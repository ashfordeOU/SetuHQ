"""The methods paper: every number comes from the committed JSON, and the pending results stay pending."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import paper_numbers as PN  # noqa: E402
from exoplan.benchmark_toi import wilson  # noqa: E402

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
    for e in lb["entries"]:
        assert pct(e["scores"]["completeness_all_stars"]) in FLAT
        assert pct(e["scores"]["fp_rejection"]) in FLAT and pct(e["scores"]["reliability"]) in FLAT


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


def test_every_doi_is_from_the_atlas_or_checked_on_crossref():
    dois = set(re.findall(r"doi:\[([^\]]+)\]", PAPER))
    known = {v["doi"] for v in REFS["refs"].values() if v["doi"]}
    assert dois == known
    assert {v["source"] for v in REFS["refs"].values()} <= {"ATLAS", "crossref"}
    assert sorted(k for k, v in REFS["refs"].items() if v["source"] == "crossref") == ["natastron2025", "wilson1927", "yu2019"]
    # Every published value cites a reference in the list.
    assert all(v["ref"] in REFS["refs"] for v in REFS["values"].values())
    # Every reference is cited in the text, except through the bibliography alone.
    for k, v in REFS["refs"].items():
        if k != "phcheops":
            assert v["cite"] in FLAT.split("## References")[0], k


def test_wording_rules():
    assert "SuperIntelligence" not in FLAT and "Superintelligence" not in FLAT
    assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in FLAT
    for bad in ("we discovered", "exoplan discovered", "we confirm", "new planet", "newly discovered"):
        assert bad not in FLAT.lower(), bad
    assert "aastex631" in FLAT and "Markdown only" in FLAT

"""Cross-provider agreement (φ) on the Sentinels' stated subsample, from stored outcomes only (no API calls)."""

import json
from pathlib import Path

import pytest

from exoplan import benchmark_toi as B
from exoplan.agreement import effective_voters, pairwise, phi

ROOT = Path(__file__).resolve().parents[1]


def test_phi_reproduces_the_stored_claude_pair():
    """The benchmark's stored figure: the two Claude personas agree on 38 of 40 stars, φ = 0.89."""
    stored = json.loads((ROOT / "docs/results/benchmark_real_tois.json").read_text())["sentinels"]["agreement"]
    # Each persona marked 14 stars (10 CP/KP, 4 FP): 13 both, 25 neither, one each the other way. 38 of 40 agree.
    pairs = [(True, True)] * 13 + [(False, False)] * 25 + [(True, False), (False, True)]
    got = phi(pairs)
    assert got["agree"] == stored["agree"] == 38 and got["n"] == stored["n"] == 40
    assert got["phi"] == pytest.approx(stored["phi"])


def test_phi_edge_cases():
    assert phi([(True, True), (True, True)])["phi"] is None  # one reviewer always says yes: φ undefined
    assert phi([(True, False), (False, True)])["phi"] == pytest.approx(-1.0)
    assert phi([])["n"] == 0


def test_pairwise_labels_same_model_and_compares_only_shared_stars():
    hits = {"a": {"claude-volunteer": True, "claude-skeptic": True, "gpt-skeptic": False},
            "b": {"claude-volunteer": False, "claude-skeptic": False, "gpt-skeptic": True},
            "c": {"claude-volunteer": True, "claude-skeptic": True}}  # the GPT Sentinel failed here: not compared
    ids = {"claude-volunteer": {"provider": "claude-code", "model": "default"},
           "claude-skeptic": {"provider": "claude-code", "model": "default"},
           "gpt-skeptic": {"provider": "openai", "model": "gpt-test"}}
    table = {(p["a"], p["b"]): p for p in pairwise(hits, list(ids), ids)}
    same = table[("claude-volunteer", "claude-skeptic")]
    assert same["same_model"] is True and same["n"] == 3 and same["phi"] == pytest.approx(1.0)
    cross = table[("claude-volunteer", "gpt-skeptic")]
    assert cross["same_model"] is False and cross["n"] == 2 and cross["phi"] == pytest.approx(-1.0)
    assert cross["b_provider"] == "openai"
    assert effective_voters(list(table.values()), list(ids)) == pytest.approx(3 / (1 + 2 * (1 / 3)))


def _sample():
    tois = [{"toi": f"{i}.01", "tic": i, "class": "positive" if i < 3 else "fp", "half": "held_out",
             "period": 3.0, "period_err": 0.001, "tranmid_bjd": 2458000.0, "tranmid_err": 0.001, "duration_hours": 2.0,
             "disposition": "CP" if i < 3 else "FP"} for i in range(1, 5)]
    return {"tois": tois}


def test_sentinel_summary_adds_a_provider_and_keeps_the_claude_pair():
    sample = _sample()
    on, off = {"label": "potential_planet", "marks": [[1.0, 1.1]]}, {"label": "noise", "marks": []}
    # Pretend match: a mark counts when its centre is below 2.
    match = lambda cand, target: cand["t_center"] < 2  # noqa: E731
    results = {
        "1.01": {"claude-volunteer": {"s": on}, "claude-skeptic": {"s": on}, "gpt-skeptic": {"s": off}},
        "2.01": {"claude-volunteer": {"s": on}, "claude-skeptic": {"s": on}, "gpt-skeptic": {"s": on}},
        "3.01": {"claude-volunteer": {"s": off}, "claude-skeptic": {"s": off}, "gpt-skeptic": {"s": on}},
        "4.01": {"claude-volunteer": {"s": off}, "claude-skeptic": {"s": off}, "gpt-skeptic": {"s": {"error": "x"}}},
    }
    data = {"subsample": list(results), "results": results,
            "reviewers": {"gpt-skeptic": {"provider": "openai", "model": "gpt-test"}}}
    se = B.sentinel_summary(data, sample, match)
    assert list(se["personas"]) == ["claude-volunteer", "claude-skeptic", "gpt-skeptic"]
    assert se["personas"]["gpt-skeptic"]["errors"] == 1
    assert se["agreement"]["phi"] == pytest.approx(1.0)  # the Claude pair, under its first name
    md = "\n".join(B._sentinel_lines(se))
    assert "gpt-skeptic on openai / gpt-test" in md and "| claude-volunteer · gpt-skeptic | not recorded |" in md
    assert "Only Claude has been benchmarked" in md


def test_sentinel_section_reads_as_before_with_only_claude():
    stored = json.loads((ROOT / "docs/results/benchmark_real_tois.json").read_text())["sentinels"]
    md = "\n".join(B._sentinel_lines(stored))
    assert "Both Sentinels (one Claude model, two personas, through the Claude Code CLI)" in md
    assert "φ = 0.89" in md and "Agreement for every pair" not in md


def test_effective_voters_leave_out_a_constant_reviewer_and_say_so():
    from exoplan.agreement import constant_reviewers

    hits = {"a": {"x": True, "y": True, "z": False}, "b": {"x": False, "y": False, "z": False},
            "c": {"x": True, "y": False, "z": False}}
    ids = ["x", "y", "z"]
    table = pairwise(hits, ids)
    assert constant_reviewers(hits, ids) == ["z"]  # z said no every time: its φ is undefined
    xy = next(p for p in table if (p["a"], p["b"]) == ("x", "y"))["phi"]
    # k counts only x and y, not z: 2 / (1 + φ_xy), not 3 / (1 + 2 φ_xy).
    assert effective_voters(table, ids, ["z"]) == pytest.approx(2 / (1 + max(0.0, xy)))
    assert effective_voters(table, ids, ["y", "z"]) is None  # fewer than two left
    sample = _sample()
    on, off = {"label": "potential_planet", "marks": [[1.0, 1.1]]}, {"label": "noise", "marks": []}
    results = {"1.01": {"claude-volunteer": {"s": on}, "claude-skeptic": {"s": on}, "gemini-volunteer": {"s": off}},
               "2.01": {"claude-volunteer": {"s": off}, "claude-skeptic": {"s": on}, "gemini-volunteer": {"s": off}},
               "3.01": {"claude-volunteer": {"s": off}, "claude-skeptic": {"s": off}, "gemini-volunteer": {"s": off}}}
    se = B.sentinel_summary({"subsample": list(results), "results": results}, sample, lambda c, t: c["t_center"] < 2)
    assert se["constant_reviewers"] == ["gemini-volunteer"] and se["effective_voters_k"] == 2
    md = "\n".join(B._sentinel_lines(se))
    assert "of k = 2" in md and "Left out of k: gemini-volunteer" in md

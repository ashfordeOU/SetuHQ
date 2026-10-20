# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json

import pytest

from setuhq.reviewers import ClaudeCodeReviewer
from setuhq.reviewers.claude import ReviewError
from setuhq.render import render_subject


def _envelope(marks, label="potential_planet"):
    answer = {"marks": [{"start": a, "end": b} for a, b in marks], "label": label,
              "noise_reason": None, "confidence": 0.7, "rationale": "dip"}
    return json.dumps({"type": "result", "subtype": "success", "result": json.dumps(answer)})


def test_claude_code_reviewer_parses_cli_envelope(tmp_path, transit_subject):
    subject, injection = transit_subject
    image = render_subject(subject, tmp_path / "s.png")
    calls = []

    def runner(cmd, cwd):
        calls.append((cmd, cwd))
        return _envelope([(injection.t_start, injection.t_end)])

    reviewer = ClaudeCodeReviewer("cc-test", runner=runner, cache_dir=tmp_path / "cache")
    result = reviewer.review(subject, image)
    assert result.label == "potential_planet"
    cmd, cwd = calls[0]
    assert cmd[:2] == ["claude", "-p"]
    assert "--allowedTools" in cmd and "Read" in cmd
    assert str(image.resolve()) in cmd[2]
    assert "TIC" not in cmd[2]


def test_claude_code_reviewer_caches(tmp_path, transit_subject):
    subject, injection = transit_subject
    image = render_subject(subject, tmp_path / "s.png")
    count = {"n": 0}

    def runner(cmd, cwd):
        count["n"] += 1
        return _envelope([(injection.t_start, injection.t_end)])

    cache = tmp_path / "cache"
    ClaudeCodeReviewer("cc", runner=runner, cache_dir=cache).review(subject, image)
    ClaudeCodeReviewer("cc", runner=runner, cache_dir=cache).review(subject, image)
    assert count["n"] == 1


def test_claude_code_reviewer_retries_bad_output(tmp_path, transit_subject, monkeypatch):
    subject, _ = transit_subject
    monkeypatch.setattr("setuhq.reviewers.claude_code.time.sleep", lambda s: None)
    image = render_subject(subject, tmp_path / "s.png")
    outputs = iter(["not json", json.dumps({"result": "no json here"}), "still not json"])
    reviewer = ClaudeCodeReviewer("cc", runner=lambda cmd, cwd: next(outputs), retries=3)
    with pytest.raises(ReviewError):
        reviewer.review(subject, image)


def test_claude_code_unavailable_without_cli(monkeypatch):
    monkeypatch.setattr("setuhq.reviewers.claude_code.shutil.which", lambda name: None)
    assert not ClaudeCodeReviewer("cc", binary="no-such-claude").available()


def test_the_model_the_cli_reports_is_recorded_with_the_date(tmp_path, transit_subject):
    subject, injection = transit_subject
    image = render_subject(subject, tmp_path / "s.png")
    answer = json.loads(_envelope([(injection.t_start, injection.t_end)]))
    answer["modelUsage"] = {"claude-test-model": {"inputTokens": 1, "outputTokens": 9}}
    cache = tmp_path / "cache"
    r = ClaudeCodeReviewer("cc", runner=lambda cmd, cwd: json.dumps(answer), cache_dir=cache)
    c = r.review(subject, image)
    assert c.metadata["model"] == "claude-test-model" and c.metadata["model_reported"] is True
    assert c.metadata["called_at"].startswith("20")
    stored = json.loads(next(cache.glob("*.json")).read_text())
    assert stored["model_reported"] == "claude-test-model" and stored["called_at"] == c.metadata["called_at"]
    # An answer cached before the model was stored says so: no reported model, no call date.
    stored.pop("model_reported"), stored.pop("called_at")
    next(cache.glob("*.json")).write_text(json.dumps(stored))
    again = ClaudeCodeReviewer("cc", runner=lambda cmd, cwd: 1 / 0, cache_dir=cache).review(subject, image)
    assert again.metadata["model_reported"] is False and again.metadata["called_at"] is None
    assert again.metadata["cached"] is True


def test_the_benchmark_counts_reviews_by_the_model_they_name():
    from setuhq.benchmark_toi import _model_label

    assert _model_label({"model": "claude-test-model", "model_reported": True}) == "claude-test-model"
    assert _model_label({"model": "claude-test-model"}) == "claude-test-model"  # stored before model_reported existed
    assert _model_label({"model": "default", "model_reported": False}) == "default (configured; not reported by the provider)"
    assert _model_label({"label": "noise"}) == _model_label({"model": None}) == "not recorded"

import json

import pytest

from exoplan.reviewers import ClaudeCodeReviewer
from exoplan.reviewers.claude import ReviewError
from exoplan.render import render_subject


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
    monkeypatch.setattr("exoplan.reviewers.claude_code.time.sleep", lambda s: None)
    image = render_subject(subject, tmp_path / "s.png")
    outputs = iter(["not json", json.dumps({"result": "no json here"}), "still not json"])
    reviewer = ClaudeCodeReviewer("cc", runner=lambda cmd, cwd: next(outputs), retries=3)
    with pytest.raises(ReviewError):
        reviewer.review(subject, image)


def test_claude_code_unavailable_without_cli(monkeypatch):
    monkeypatch.setattr("exoplan.reviewers.claude_code.shutil.which", lambda name: None)
    assert not ClaudeCodeReviewer("cc", binary="no-such-claude").available()

import json
from types import SimpleNamespace

import pytest

from setuhq.reviewers import ClaudeReviewer, SimulatedVolunteer
from setuhq.reviewers.base import NOISE, POTENTIAL_PLANET, Classification, Mark
from setuhq.reviewers.claude import ReviewError, build_prompt, parse_response
from setuhq.render import render_subject


class FakeMessages:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        text = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        if isinstance(text, Exception):
            raise text
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, texts):
        self.messages = FakeMessages(texts)


def _answer(marks, label="potential_planet", **extra):
    payload = {"marks": [{"start": a, "end": b} for a, b in marks], "label": label, "noise_reason": None,
               "confidence": 0.8, "rationale": "dip"}
    payload.update(extra)
    return json.dumps(payload)


def test_parse_response_clips_marks_to_subject_range(transit_subject):
    subject, _ = transit_subject
    text = _answer([(subject.start - 1, subject.start + 0.5), (subject.end - 0.5, subject.end + 9)])
    result = parse_response(text, subject, "claude-x")
    assert result.label == POTENTIAL_PLANET
    assert len(result.marks) == 2
    assert result.marks[0].t_start == subject.start
    assert result.marks[1].t_end == subject.end


def test_parse_response_downgrades_planet_without_marks(transit_subject):
    subject, _ = transit_subject
    result = parse_response(_answer([]), subject, "claude-x")
    assert result.label == NOISE
    assert result.reason == "other"


def test_parse_response_accepts_json_inside_prose(transit_subject):
    subject, _ = transit_subject
    text = "Here is my answer:\n" + _answer([(6.0, 6.2)]) + "\nThanks."
    assert parse_response(text, subject, "c").marks


def test_parse_response_rejects_garbage(transit_subject):
    subject, _ = transit_subject
    with pytest.raises(ReviewError):
        parse_response("no json here", subject, "c")
    with pytest.raises(ReviewError):
        parse_response('{"label": "maybe"}', subject, "c")


def test_build_prompt_hides_target_identity(transit_subject):
    subject, _ = transit_subject
    system, user = build_prompt(subject, "volunteer")
    assert "TIC" not in user and "TIC" not in system
    assert subject.subject_id in user
    with pytest.raises(ValueError):
        build_prompt(subject, "nobody")


def test_claude_reviewer_uses_client_and_parses(tmp_path, transit_subject):
    subject, injection = transit_subject
    image = render_subject(subject, tmp_path / "s.png")
    client = FakeClient([_answer([(injection.t_start, injection.t_end)])])
    reviewer = ClaudeReviewer("claude-test", client=client, cache_dir=tmp_path / "cache")
    result = reviewer.review(subject, image)
    assert result.label == POTENTIAL_PLANET
    assert client.messages.calls == 1


def test_claude_reviewer_cache_avoids_second_call(tmp_path, transit_subject):
    subject, injection = transit_subject
    image = render_subject(subject, tmp_path / "s.png")
    client = FakeClient([_answer([(injection.t_start, injection.t_end)])])
    cache = tmp_path / "cache"
    first = ClaudeReviewer("claude-test", client=client, cache_dir=cache).review(subject, image)
    second = ClaudeReviewer("claude-test", client=client, cache_dir=cache).review(subject, image)
    assert client.messages.calls == 1
    assert first.marks == second.marks


def test_claude_reviewer_retries_then_fails(tmp_path, transit_subject, monkeypatch):
    subject, _ = transit_subject
    monkeypatch.setattr("setuhq.reviewers.claude.time.sleep", lambda s: None)
    image = render_subject(subject, tmp_path / "s.png")
    client = FakeClient([RuntimeError("boom")])
    reviewer = ClaudeReviewer("claude-test", client=client, retries=2)
    with pytest.raises(ReviewError):
        reviewer.review(subject, image)
    assert client.messages.calls == 2


def test_claude_reviewer_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not ClaudeReviewer("claude-test").available()


def test_simulated_volunteer_is_deterministic_and_finds_transit(transit_subject):
    subject, injection = transit_subject
    volunteer = SimulatedVolunteer("vol", snr_threshold=5.0, miss_probability=0.0, seed=3)
    first = volunteer.review(subject)
    second = volunteer.review(subject)
    assert first.marks == second.marks
    assert first.label == POTENTIAL_PLANET
    assert any(injection.hit_by(m.center) for m in first.marks)


def test_classification_validates_label_and_reason():
    with pytest.raises(ValueError):
        Classification("r", "s", "planet!")
    with pytest.raises(ValueError):
        Classification("r", "s", NOISE, reason="aliens")
    with pytest.raises(ValueError):
        Mark(2.0, 1.0)


def test_parse_response_skips_prose_braces(transit_subject):
    subject, _ = transit_subject
    text = '{"label": "noise", "marks": []} (see {note} for details)'
    result = parse_response(text, subject, "c")
    assert result.label == "noise"

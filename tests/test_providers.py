"""Sentinels on every provider: one task, one schema, validated and clipped the same way. No network: each
provider's HTTP answer is mocked, including malformed JSON, refusals, timeouts and answers in the wrong schema."""

import json
import socket
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from exoplan.calibrate import WEIGHT_FLOOR, apply_calibration, calibration_record, identity
from exoplan.config import RunConfig, build_reviewers
from exoplan.pipeline import run_pipeline
from exoplan.render import render_subject
from exoplan.reviewers import (
    ClaudeCodeReviewer,
    ClaudeReviewer,
    GeminiReviewer,
    OpenAICompatibleReviewer,
    OpenAIReviewer,
    SimulatedVolunteer,
)
from exoplan.reviewers.http import ProviderTimeout, post_json
from exoplan.reviewers.sentinel import RefusalError
from exoplan.reviewers.task import PROMPT_VERSION, ReviewError

SECRET = "sk-test-NEVER-WRITE-THIS"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("exoplan.reviewers.sentinel.time.sleep", lambda s: None)


@pytest.fixture
def keys(monkeypatch):
    for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.setenv(var, SECRET)


@pytest.fixture
def image(tmp_path, transit_subject):
    subject, injection = transit_subject
    return subject, injection, render_subject(subject, tmp_path / "s.png")


def answer(marks, label="potential_planet", **extra):
    payload = {"marks": [{"start": a, "end": b} for a, b in marks], "label": label, "noise_reason": None,
               "confidence": 0.8, "rationale": "a flat-bottomed dip"}
    return json.dumps(payload | extra)


def chat(text, model="gpt-test-2026-01-01", **message):
    return {"id": "x", "model": model, "choices": [{"index": 0, "finish_reason": "stop",
                                                     "message": {"role": "assistant", "content": text, **message}}]}


def gemini(text, model="gemini-test-001", finish="STOP", thought=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}], "modelVersion": model}


class Fake:
    """A transport that records each request and plays back answers (an Exception is raised)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        nxt = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# ---------------------------------------------------------------- each provider, a good answer


def test_openai_request_and_provenance(keys, image, tmp_path):
    subject, inj, png = image
    fake = Fake(chat(answer([(inj.t_start, inj.t_end)])))
    r = OpenAIReviewer("gpt-skeptic", model="gpt-test", persona="skeptic", transport=fake, cache_dir=tmp_path / "c")
    c = r.review(subject, png)
    assert c.label == "potential_planet" and len(c.marks) == 1
    call = fake.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"] == {"Authorization": f"Bearer {SECRET}"}
    body = call["body"]
    assert body["model"] == "gpt-test" and body["response_format"] == {"type": "json_object"}
    assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "TIC" not in json.dumps(body["messages"][1]["content"][0])  # blind: no target identity
    # The exact model id the API reported, the provider, the call time and the prompt version are recorded.
    m = c.metadata
    assert m["provider"] == "openai" and m["model"] == "gpt-test-2026-01-01" and m["model_reported"] is True
    assert m["prompt_version"] == PROMPT_VERSION and m["persona"] == "skeptic" and m["called_at"].endswith("+00:00")
    assert m["cached"] is False


def test_gemini_request_and_provenance(keys, image):
    subject, inj, png = image
    fake = Fake(gemini(answer([(inj.t_start, inj.t_end)]), thought='{"label": "noise"} thinking aloud'))
    c = GeminiReviewer("gemini-volunteer", model="gemini-test", transport=fake).review(subject, png)
    call = fake.calls[0]
    assert call["url"].endswith("/models/gemini-test:generateContent") and SECRET not in call["url"]
    assert call["headers"] == {"x-goog-api-key": SECRET}
    assert call["body"]["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "image/png"
    assert call["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert c.label == "potential_planet"  # the thought part is not read as the answer
    assert c.metadata["provider"] == "gemini" and c.metadata["model"] == "gemini-test-001"


@pytest.mark.parametrize("cfg, url, headers", [
    ({"base_url": "http://localhost:11434/v1"}, "http://localhost:11434/v1/chat/completions", {}),  # Ollama: no key
    ({"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
     "https://openrouter.ai/api/v1/chat/completions", {"Authorization": f"Bearer {SECRET}"}),
    ({"base_url": "https://res.openai.azure.com/openai/v1/", "api_key_env": "AZURE_OPENAI_API_KEY", "auth": "api-key",
      "query": {"api-version": "preview"}},
     "https://res.openai.azure.com/openai/v1/chat/completions?api-version=preview", {"api-key": SECRET}),
])
def test_openai_compatible_endpoints(keys, image, cfg, url, headers):
    subject, inj, png = image
    fake = Fake(chat(answer([(inj.t_start, inj.t_end)]), model="llava:13b"))
    r = OpenAICompatibleReviewer("local-volunteer", model="llava", transport=fake, **cfg)
    assert r.available()
    c = r.review(subject, png)
    assert fake.calls[0]["url"] == url and fake.calls[0]["headers"] == headers
    assert "max_tokens" in fake.calls[0]["body"] and "response_format" not in fake.calls[0]["body"]
    assert c.metadata["provider"] == "openai-compatible" and c.metadata["model"] == "llava:13b"
    from urllib.parse import urlsplit

    recorded = c.metadata["endpoint"]  # scheme, host and port, plus a hash of the path: no path or query recorded
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(cfg["base_url"]))
    assert recorded.startswith(origin + " [path sha256:") and urlsplit(cfg["base_url"]).path not in recorded


def test_anthropic_records_reported_model_and_refusal(image, tmp_path):
    subject, inj, png = image

    class Messages:
        def __init__(self, response):
            self.response, self.calls = response, 0

        def create(self, **kw):
            self.calls += 1
            return self.response

    good = SimpleNamespace(model="claude-test-20260101", stop_reason="end_turn",
                           content=[SimpleNamespace(type="text", text=answer([(inj.t_start, inj.t_end)]))])
    c = ClaudeReviewer("claude-volunteer", client=SimpleNamespace(messages=Messages(good))).review(subject, png)
    assert c.metadata["provider"] == "anthropic" and c.metadata["model"] == "claude-test-20260101"
    refusal = Messages(SimpleNamespace(model="m", stop_reason="refusal", content=[]))
    with pytest.raises(RefusalError):
        ClaudeReviewer("claude-skeptic", client=SimpleNamespace(messages=refusal), retries=3).review(subject, png)
    assert refusal.calls == 1  # a refusal is not retried


def test_claude_code_reads_model_from_model_usage(image):
    subject, inj, png = image
    envelope = {"type": "result", "result": answer([(inj.t_start, inj.t_end)]),
                "modelUsage": {"claude-haiku-x": {"outputTokens": 12}, "claude-opus-x": {"outputTokens": 340}}}
    c = ClaudeCodeReviewer("claude-skeptic", runner=lambda cmd, cwd: json.dumps(envelope)).review(subject, png)
    assert c.metadata["provider"] == "claude-code" and c.metadata["model"] == "claude-opus-x"
    plain = ClaudeCodeReviewer("claude-volunteer", runner=lambda cmd, cwd: json.dumps({"result": envelope["result"]}))
    m = plain.review(subject, png).metadata
    assert m["model"] == "default" and m["model_reported"] is False


# ---------------------------------------------------------------- bad answers, on every HTTP provider


def _http(kind, fake):
    if kind == "openai":
        return OpenAIReviewer("r", model="m", transport=fake, retries=3)
    if kind == "gemini":
        return GeminiReviewer("r", model="m", transport=fake, retries=3)
    return OpenAICompatibleReviewer("r", model="m", base_url="http://localhost:1/v1", transport=fake, retries=3)


def _wrap(kind, text, **kw):
    return gemini(text, **kw) if kind == "gemini" else chat(text, **kw)


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
@pytest.mark.parametrize("bad", ["not json at all", '{"marks": [], "label": "maybe"}', '{"marks": []}', ""])
def test_malformed_or_wrong_schema_is_retried_then_skipped(keys, image, kind, bad):
    subject, _, png = image
    fake = Fake(_wrap(kind, bad))
    with pytest.raises(ReviewError):
        _http(kind, fake).review(subject, png)
    assert len(fake.calls) == 3


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
def test_timeout_is_retried_then_a_good_answer_is_used(keys, image, kind):
    subject, inj, png = image
    fake = Fake(ProviderTimeout("timed out"), _wrap(kind, answer([(inj.t_start, inj.t_end)])))
    c = _http(kind, fake).review(subject, png)
    assert c.label == "potential_planet" and len(fake.calls) == 2


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
def test_timeouts_every_time_end_in_review_error(keys, image, kind):
    subject, _, png = image
    fake = Fake(ProviderTimeout("timed out"))
    with pytest.raises(ReviewError, match="timed out"):
        _http(kind, fake).review(subject, png)
    assert len(fake.calls) == 3


@pytest.mark.parametrize("kind, refusal", [
    ("openai", chat(None, refusal="I can't help with that.")),
    ("openai_compatible", {"model": "m", "choices": [{"finish_reason": "content_filter", "message": {"content": ""}}]}),
    ("gemini", {"promptFeedback": {"blockReason": "SAFETY"}}),
    ("gemini", gemini("", finish="SAFETY")),
])
def test_refusal_is_not_retried(keys, image, kind, refusal):
    subject, _, png = image
    fake = Fake(refusal)
    with pytest.raises(RefusalError):
        _http(kind, fake).review(subject, png)
    assert len(fake.calls) == 1


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
def test_provider_error_body_is_a_review_error(keys, image, kind):
    subject, _, png = image
    with pytest.raises(ReviewError):
        _http(kind, Fake({"error": {"message": "model not found"}})).review(subject, png)


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
def test_marks_are_clipped_and_bad_values_dropped_whatever_the_provider(keys, image, kind):
    subject, inj, png = image
    text = json.dumps({"marks": [{"start": subject.start - 50, "end": subject.start + 0.5},  # clipped to the range
                                 {"start": subject.end + 1, "end": subject.end + 2},       # outside: dropped
                                 {"start": "x", "end": 3}, {"start": 5}],                   # unusable: dropped
                       "label": "potential_planet", "noise_reason": "made_up", "confidence": 7, "rationale": "r" * 900})
    c = _http(kind, Fake(_wrap(kind, text))).review(subject, png)
    assert len(c.marks) == 1 and c.marks[0].t_start == subject.start
    assert c.confidence == 1.0 and len(c.rationale) == 500 and c.reason is None


@pytest.mark.parametrize("kind", ["openai", "gemini", "openai_compatible"])
def test_answer_inside_prose_is_found(keys, image, kind):
    subject, inj, png = image
    text = "Sure! Here is the JSON {not this}: " + answer([(inj.t_start, inj.t_end)]) + " Hope it helps."
    assert _http(kind, Fake(_wrap(kind, text))).review(subject, png).label == "potential_planet"


# ---------------------------------------------------------------- cache


def test_cache_keys_differ_by_provider_and_model(keys, image, tmp_path):
    subject, inj, png = image
    good_chat, good_gem = chat(answer([(inj.t_start, inj.t_end)])), gemini(answer([(inj.t_start, inj.t_end)]))
    cache = tmp_path / "cache"
    reviewers = [
        OpenAIReviewer("a", model="model-1", transport=Fake(good_chat), cache_dir=cache),
        OpenAIReviewer("b", model="model-2", transport=Fake(good_chat), cache_dir=cache),
        GeminiReviewer("c", model="model-1", transport=Fake(good_gem), cache_dir=cache),
        OpenAICompatibleReviewer("d", model="model-1", base_url="http://localhost:11434/v1", transport=Fake(good_chat), cache_dir=cache),
        OpenAICompatibleReviewer("e", model="model-1", base_url="http://gpu-box:8000/v1", transport=Fake(good_chat), cache_dir=cache),
        ClaudeCodeReviewer("f", model="model-1", runner=lambda cmd, cwd: json.dumps({"result": answer([(1, 2)])}), cache_dir=cache),
    ]
    for r in reviewers:
        r.review(subject, png)
    assert len(list(cache.glob("*.json"))) == len(reviewers)  # one answer each: none shared


def test_cache_hit_keeps_provenance_and_never_stores_the_key(keys, image, tmp_path):
    subject, inj, png = image
    fake = Fake(chat(answer([(inj.t_start, inj.t_end)])))
    cache = tmp_path / "cache"
    first = OpenAIReviewer("gpt-volunteer", model="gpt-test", transport=fake, cache_dir=cache).review(subject, png)
    second = OpenAIReviewer("gpt-volunteer", model="gpt-test", transport=fake, cache_dir=cache).review(subject, png)
    assert len(fake.calls) == 1 and second.marks == first.marks
    assert second.metadata["cached"] is True and second.metadata["called_at"] == first.metadata["called_at"]
    assert second.metadata["model"] == "gpt-test-2026-01-01"
    stored = json.loads(next(cache.glob("*.json")).read_text())
    assert set(stored) == {"provider", "model_requested", "model_reported", "called_at", "prompt_version", "text"}
    assert SECRET not in next(cache.glob("*.json")).read_text()


def test_claude_code_cache_key_is_unchanged(image, tmp_path):
    """Answers cached by the Claude Code Sentinel before providers existed are still found (same key formula)."""
    import hashlib

    subject, inj, png = image
    reviewer = ClaudeCodeReviewer("cc", runner=lambda cmd, cwd: json.dumps({"result": answer([(1, 2)])}), cache_dir=tmp_path)
    from exoplan.reviewers.task import build_prompt

    system, user = build_prompt(subject, "volunteer")
    request = reviewer.backend.request(system, user, png.resolve())
    legacy = hashlib.sha256("\x1f".join([PROMPT_VERSION, "claude-code", "default", "volunteer", request]).encode()
                            + hashlib.sha256(png.read_bytes()).digest()).hexdigest()
    (tmp_path / f"{legacy}.json").write_text(json.dumps({"backend": "claude-code", "text": answer([(inj.t_start, inj.t_end)])}))
    c = reviewer.review(subject, png)
    assert c.metadata["cached"] is True and c.metadata["called_at"] is None and len(c.marks) == 1


# ---------------------------------------------------------------- keys, availability, the manifest


def test_missing_keys_make_providers_unavailable_with_a_reason(monkeypatch):
    for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert OpenAIReviewer("a", model="m").unavailable_reason() == "OPENAI_API_KEY is not set"
    assert GeminiReviewer("b", model="m").unavailable_reason() == "GEMINI_API_KEY is not set"
    assert ClaudeReviewer("c").unavailable_reason() == "ANTHROPIC_API_KEY is not set"
    assert not OpenAICompatibleReviewer("d", model="m", base_url="https://openrouter.ai/api/v1",
                                        api_key_env="OPENROUTER_API_KEY").available()
    assert OpenAICompatibleReviewer("e", model="m", base_url="http://localhost:11434/v1").available()


def test_anthropic_without_sdk_is_unavailable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setattr("exoplan.reviewers.claude.importlib.util.find_spec", lambda name: None)
    assert "anthropic package is not installed" in ClaudeReviewer("c").unavailable_reason()


def test_config_builds_a_mixed_panel_and_refuses_keys_in_the_file(tmp_path):
    specs = [{"type": "simulated", "id": "volunteer-typical"},
             {"type": "claude_code", "id": "claude-volunteer", "persona": "volunteer"},
             {"type": "openai", "id": "gpt-skeptic", "persona": "skeptic", "model": "gpt-test"},
             {"type": "gemini", "id": "gemini-volunteer", "model": "gemini-test"},
             {"type": "openai_compatible", "id": "local-skeptic", "persona": "skeptic", "model": "llava",
              "base_url": "http://localhost:11434/v1"}]
    panel = build_reviewers(specs, cache_root=tmp_path)
    assert [r.kind for r in panel] == ["simulated", "claude_code", "openai", "gemini", "openai_compatible"]
    assert [getattr(r, "provider", None) for r in panel] == [None, "claude-code", "openai", "gemini", "openai-compatible"]
    assert panel[2].cache_dir == str(tmp_path / "openai")
    with pytest.raises(ValueError, match="environment"):
        build_reviewers([{"type": "openai", "id": "x", "model": "m", "api_key": "sk-..."}])
    with pytest.raises(ValueError, match="model"):
        build_reviewers([{"type": "gemini", "id": "x"}])


def test_manifest_records_skips_providers_and_uncalibrated_weights(monkeypatch, tmp_path, lightcurve_with_transits):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls = Fake(chat(answer([(2.4, 2.6)]), model="gpt-test-2026-01-01"))
    reviewers = [SimulatedVolunteer("vol-a", seed=1),
                 OpenAIReviewer("gpt-skeptic", model="gpt-test", persona="skeptic", transport=calls),
                 GeminiReviewer("gemini-volunteer", model="gemini-test")]
    config = RunConfig(name="mixed", subject_days=13.0, min_points=100, fap_trials=0, fit_transits=False)
    summary = run_pipeline(config, [lightcurve_with_transits], reviewers, tmp_path / "run", weights={"vol-a": 0.6},
                           weights_source="test weights")
    assert summary.skipped_reviewers == ["gemini-volunteer"]
    text = (tmp_path / "run" / "manifest.json").read_text()
    assert SECRET not in text
    manifest = json.loads(text)
    assert manifest["skipped_reviewers_detail"] == [{"id": "gemini-volunteer", "kind": "gemini", "provider": "gemini",
                                                     "model": "gemini-test", "reason": "GEMINI_API_KEY is not set"}]
    by_id = {r["id"]: r for r in manifest["reviewers"]}
    assert by_id["vol-a"]["weight"] == 0.6 and by_id["vol-a"]["calibration"] == "calibrated"
    gpt = by_id["gpt-skeptic"]
    assert gpt["weight"] == WEIGHT_FLOOR and gpt["calibration"] == "uncalibrated"
    assert gpt["provider"] == "openai" and gpt["model"] == "gpt-test" and gpt["persona"] == "skeptic"
    assert gpt["models_reported"] == ["gpt-test-2026-01-01"] and gpt["called_at"]["first"]
    assert manifest["weights"]["gpt-skeptic"] == WEIGHT_FLOOR
    assert manifest["sentinel_prompt_version"] == PROMPT_VERSION
    rows = (tmp_path / "run" / "classifications.csv").read_text()
    assert "gpt-test-2026-01-01" in rows and '""provider"": ""openai""' in rows and SECRET not in rows


def test_weights_apply_only_to_the_provider_and_model_they_were_measured_on(keys):
    a = OpenAIReviewer("gpt-skeptic", model="gpt-new")
    b = ClaudeCodeReviewer("claude-skeptic", runner=lambda c, w: "")
    probe = SimulatedVolunteer("vol-a")
    record = calibration_record({}, weights_file="w.json")
    record["reviewers"] = {"gpt-skeptic": {"tpr": 0.7, "fpr": 0.1, "weight": 0.6, "provider": "openai", "model": "gpt-old"},
                           "claude-skeptic": {"tpr": 0.5, "fpr": 0.0, "weight": 0.5}}  # an older record: no provider stored
    w, basis = apply_calibration([a, b, probe], {"gpt-skeptic": 0.6, "claude-skeptic": 0.5}, record)
    assert w["gpt-skeptic"] == WEIGHT_FLOOR and basis["gpt-skeptic"]["status"] == "uncalibrated"
    assert "gpt-old" in basis["gpt-skeptic"]["note"]
    assert w["claude-skeptic"] == 0.5 and basis["claude-skeptic"]["status"] == "calibrated"
    assert "claude-code / default only" in basis["claude-skeptic"]["note"]
    assert w["vol-a"] == 1.0 and basis["vol-a"]["status"] == "uncalibrated"
    w, basis = apply_calibration([a, probe], None)
    assert w == {"gpt-skeptic": 1.0, "vol-a": 1.0} and {b["status"] for b in basis.values()} == {"uniform"}
    assert identity(a) == {"provider": "openai", "model": "gpt-new"} and identity(probe) == {}


def test_resolve_weights_keeps_calibrated_probes_and_floors_a_new_sentinel(tmp_path):
    from exoplan.cli import resolve_weights

    default = tmp_path / "w.json"
    default.write_text(json.dumps({"vol-a": 0.6, "claude-skeptic": 0.5}))
    cfg = SimpleNamespace(reviewers=({"type": "simulated", "id": "vol-a"}, {"type": "claude_code", "id": "claude-skeptic"},
                                     {"type": "openai", "id": "gpt-skeptic", "model": "m"}))
    weights, source = resolve_weights(cfg, None, str(default))
    assert weights == {"vol-a": 0.6, "claude-skeptic": 0.5} and "gpt-skeptic" in source and "floor" in source
    cfg_probe = SimpleNamespace(reviewers=({"type": "simulated", "id": "vol-a"}, {"type": "simulated", "id": "vol-new"}))
    assert resolve_weights(cfg_probe, None, str(default))[0] is None  # a new Probe: uniform, as before


# ---------------------------------------------------------------- the plain HTTP transport, offline


def test_post_json_maps_timeouts_and_http_errors_without_leaking_headers(monkeypatch):
    import io

    def timeout(*a, **k):
        raise socket.timeout("slow")

    monkeypatch.setattr("exoplan.reviewers.http.urllib.request.urlopen", timeout)
    with pytest.raises(ProviderTimeout):
        post_json("https://api.example.test/v1/x", {"Authorization": f"Bearer {SECRET}"}, {}, 1.0)

    def http_error(*a, **k):
        raise urllib.error.HTTPError("https://api.example.test/v1/x", 401, "no", {}, io.BytesIO(b'{"error": "bad key"}'))

    monkeypatch.setattr("exoplan.reviewers.http.urllib.request.urlopen", http_error)
    with pytest.raises(ReviewError) as err:
        post_json("https://api.example.test/v1/x?key=abc", {"Authorization": f"Bearer {SECRET}"}, {}, 1.0)
    assert "HTTP 401" in str(err.value) and SECRET not in str(err.value) and "key=abc" not in str(err.value)

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("exoplan.reviewers.http.urllib.request.urlopen", lambda *a, **k: Resp(b"<html>oops"))
    with pytest.raises(ReviewError, match="did not answer with JSON"):
        post_json("https://api.example.test/v1/x", {}, {}, 1.0)


def test_example_mixed_panel_config_builds_three_providers(tmp_path):
    from exoplan.config import load_config
    from exoplan.names import display_name

    config = load_config("examples/panels/mixed_providers.toml")
    panel = [r for r in build_reviewers(config.reviewers, cache_root=tmp_path) if hasattr(r, "provider")]
    assert [(r.reviewer_id, r.provider, r.persona) for r in panel] == [
        ("claude-volunteer", "claude-code", "volunteer"), ("gpt-skeptic", "openai", "skeptic"),
        ("gemini-volunteer", "gemini", "volunteer")]
    assert [display_name(r.reviewer_id, r.kind) for r in panel] == ["Sentinel · Volunteer", "Sentinel · Skeptic",
                                                                     "Sentinel · Volunteer"]


# ---------------------------------------------------------------- review fixes: calibration, keys, retries


COMMITTED_WEIGHTS = Path(__file__).resolve().parents[1] / "docs/results/reviewer_weights_full_panel.json"


def _committed():
    from exoplan.calibrate import calibration_path

    return json.loads(COMMITTED_WEIGHTS.read_text()), json.loads(calibration_path(COMMITTED_WEIGHTS).read_text())


def test_committed_calibration_record_names_provider_and_model():
    _, record = _committed()
    for rid in ("claude-volunteer", "claude-skeptic"):
        assert record["reviewers"][rid]["provider"] == "claude-code" and record["reviewers"][rid]["model"] == "default"


@pytest.mark.parametrize("strip", [False, True])
def test_another_model_under_a_claude_id_does_not_inherit_its_weight(keys, strip):
    """An OpenAI reviewer reusing a Claude id, or Claude Code with another model, gets the floor, whether or not
    the record stores a provider (a record without one holds for claude-code / default only)."""
    weights, record = _committed()
    if strip:  # an older record, written before providers were stored
        for entry in record["reviewers"].values():
            entry.pop("provider", None), entry.pop("model", None)
    gpt = OpenAIReviewer("claude-skeptic", model="gpt-5")
    changed = ClaudeCodeReviewer("claude-volunteer", model="claude-other-model", runner=lambda c, w: "")
    api = ClaudeReviewer("claude-volunteer", model="claude-sonnet-5-5")
    same = ClaudeCodeReviewer("claude-skeptic", runner=lambda c, w: "")
    for reviewer in (gpt, changed, api):
        w, basis = apply_calibration([reviewer], weights, record)
        assert w[reviewer.reviewer_id] == WEIGHT_FLOOR and basis[reviewer.reviewer_id]["status"] == "uncalibrated"
    w, basis = apply_calibration([same, SimulatedVolunteer("volunteer-typical")], weights, record)
    assert w["claude-skeptic"] == 0.5 and basis["claude-skeptic"]["status"] == "calibrated"
    assert w["volunteer-typical"] == 0.6


def test_credentials_in_an_endpoint_are_refused_and_never_echoed(keys):
    for url in (f"https://user:{SECRET}@host.example/v1", f"https://{SECRET}@host.example/v1"):
        with pytest.raises(ValueError) as err:
            OpenAICompatibleReviewer("x", model="m", base_url=url)
        assert SECRET not in str(err.value)
    for name in ("key", "API-KEY", "api_key", "Token", "sig", "signature", "code", "secret", "password"):
        with pytest.raises(ValueError) as err:
            OpenAICompatibleReviewer("x", model="m", base_url="https://h.example/v1", query={name: SECRET})
        assert SECRET not in str(err.value)
    with pytest.raises(ValueError):
        OpenAICompatibleReviewer("x", model="m", base_url=f"https://h.example/v1?key={SECRET}")
    with pytest.raises(ValueError):
        GeminiReviewer("x", model="m", base_url=f"https://u:{SECRET}@g.example/v1beta")
    with pytest.raises(ValueError):
        build_reviewers([{"type": "openai_compatible", "id": "x", "model": "m", "base_url": f"https://u:{SECRET}@h/v1"}])
    # Allowed: a query without a credential (Azure's api-version).
    OpenAICompatibleReviewer("x", model="m", base_url="https://h.example/openai/v1", query={"api-version": "preview"})


def test_recorded_endpoint_never_carries_userinfo():
    from exoplan.reviewers.http import safe_url

    assert safe_url(f"https://u:{SECRET}@h.example:8443") == "https://h.example:8443"
    one, two = safe_url("http://localhost:11434/v1"), safe_url("http://localhost:11434/v2?x=1")
    assert one.startswith("http://localhost:11434 [path sha256:") and one != two and "v1" not in one
    assert SECRET not in safe_url(f"https://u:{SECRET}@h.example/{SECRET}?q={SECRET}")


def test_endpoint_screen_hardening(monkeypatch):
    """More credential names, a provider key's value anywhere, fragments, ;params and token-like path segments."""
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    monkeypatch.setenv("MY_ENDPOINT_KEY", "local-key-value-1234")
    base = "https://h.example/v1"
    for name in ("x-api-key", "Subscription-Key", "authorization", "client_secret", "access-key", "access_key"):
        with pytest.raises(ValueError, match="look like a credential"):
            OpenAICompatibleReviewer("x", model="m", base_url=base, query={name: "v"})
    for query in ({"note": SECRET}, {"tenant": "local-key-value-1234"}):
        with pytest.raises(ValueError) as err:
            OpenAICompatibleReviewer("x", model="m", base_url=base, query=query, api_key_env="MY_ENDPOINT_KEY")
        assert SECRET not in str(err.value) and "local-key-value-1234" not in str(err.value)
    bad_urls = [f"{base}#frag", "https://h.example/v1;jsessionid=abc", f"https://h.example/{'A1b2C3d4' * 3}/v1",
                f"https://h.example/v1?note={SECRET}"]
    for url in bad_urls:
        with pytest.raises(ValueError) as err:
            OpenAICompatibleReviewer("x", model="m", base_url=url)
        assert SECRET not in str(err.value)
    # Ordinary endpoints still pass.
    for url in ("http://localhost:11434/v1", "https://openrouter.ai/api/v1", "https://res.openai.azure.com/openai/v1"):
        OpenAICompatibleReviewer("x", model="m", base_url=url, query={"api-version": "2025-01-01-preview"})


def test_redaction_covers_wider_keys_and_base64():
    import base64

    from exoplan.reviewers.http import _secrets, redact

    key = "abc+def/ghi=jkl-mno_pqr"
    headers = {"Authorization": f"Bearer {key}"}
    b64 = base64.b64encode(key.encode()).decode()
    text = f"echo {key} | b64 {b64} | url {base64.urlsafe_b64encode(key.encode()).decode().rstrip('=')} | sk-ab+cd/ef=gh12"
    out = redact(text, _secrets(headers))
    assert key not in out and b64 not in out and b64.rstrip("=") not in out and "sk-ab+cd/ef=gh12" not in out


def test_a_key_string_reaches_no_manifest_cache_or_exception(monkeypatch, tmp_path, lightcurve_with_transits):
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRET)
    leaky = {"error": {"message": f"Incorrect API key provided: {SECRET}. Bearer {SECRET}"}}
    good = chat(answer([(2.4, 2.6)]))
    errors = []

    def transport(url, headers, body, timeout):
        assert SECRET not in url and SECRET not in json.dumps(body)
        if len(errors) < 1:
            errors.append(1)
            return leaky
        return good

    r = OpenAICompatibleReviewer("compat-skeptic", model="m", base_url="https://openrouter.ai/api/v1",
                                 api_key_env="OPENROUTER_API_KEY", transport=transport, cache_dir=tmp_path / "cache",
                                 retries=1)
    config = RunConfig(name="leak", subject_days=13.0, min_points=100, fap_trials=0, fit_transits=False)
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_pipeline(config, [lightcurve_with_transits], [r], tmp_path / "run")
    assert caught and all(SECRET not in str(w.message) for w in caught)  # the first review failed, redacted
    for path in [*(tmp_path / "run").rglob("*.json"), *(tmp_path / "run").rglob("*.csv"), *(tmp_path / "cache").glob("*.json")]:
        assert SECRET not in path.read_text(), path


@pytest.mark.parametrize("code, retried", [(401, False), (403, False), (400, False), (404, False), (429, True), (500, True)])
def test_auth_and_bad_request_errors_fail_fast(monkeypatch, image, keys, code, retried):
    import io

    subject, _, png = image
    calls = []

    def http_error(*a, **k):
        calls.append(1)
        raise urllib.error.HTTPError("https://api.openai.com/v1/chat/completions", code, "no", {},
                                     io.BytesIO(f'{{"error": "bad key {SECRET}"}}'.encode()))

    monkeypatch.setattr("exoplan.reviewers.http.urllib.request.urlopen", http_error)
    with pytest.raises(ReviewError) as err:
        OpenAIReviewer("r", model="m", retries=3).review(subject, png)
    assert len(calls) == (3 if retried else 1)
    assert SECRET not in str(err.value) and f"HTTP {code}" in str(err.value)


def test_anthropic_auth_error_fails_fast(monkeypatch, image):
    subject, _, png = image
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)

    class AuthError(Exception):
        status_code = 401

    class Messages:
        calls = 0

        def create(self, **kw):
            Messages.calls += 1
            raise AuthError(f"invalid x-api-key {SECRET}")

    with pytest.raises(ReviewError) as err:
        ClaudeReviewer("c", client=SimpleNamespace(messages=Messages()), retries=3).review(subject, png)
    assert Messages.calls == 1 and SECRET not in str(err.value)


def test_redact_removes_tokens_and_the_configured_key():
    from exoplan.reviewers.http import redact

    text = f'Bearer abc.def-123 key={SECRET} "api_key": "zzz-999" sk-proj-ABCDEFGH1234 AIza{"x" * 30} plain {SECRET}'
    out = redact(text, [SECRET])
    for gone in (SECRET, "abc.def-123", "zzz-999", "sk-proj-ABCDEFGH1234", "AIza" + "x" * 30):
        assert gone not in out
    assert "plain" in out

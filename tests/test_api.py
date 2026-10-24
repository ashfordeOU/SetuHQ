# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The stable public API (setuhq.api, docs/API.md), the standard Probe panel, the packaged weights, and keys passed
per call (C1 to C4)."""

from __future__ import annotations

import json
import pickle
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

STABLE = ["__version__", "RunConfig", "load_config", "build_reviewers", "standard_probes", "default_weights",
          "default_weights_path", "packaged_weights_path", "apply_calibration", "SimulatedVolunteer", "ClaudeReviewer",
          "OpenAIReviewer", "OpenAICompatibleReviewer", "GeminiReviewer", "Secret", "LightCurve", "load_tess",
          "load_spoc_file", "load_csv", "run_pipeline", "aggregate", "fit_transit", "transit_model", "ATTRIBUTION",
          "PROBES_ONLY", "dip_state", "dip_count"]


def test_the_stable_names_are_pinned_and_documented():
    import setuhq.api as api

    assert api.__all__ == STABLE, "a change to the stable API needs docs/API.md, the CHANGELOG and this list"
    for name in STABLE:
        assert getattr(api, name) is not None
    doc = (ROOT / "docs" / "API.md").read_text()
    for name in STABLE:
        assert f"`{name}" in doc, name
    assert "load_cheops" not in api.__all__ and "CC BY-NC 3.0 IGO" in doc


def test_standard_probes_match_the_sweep_config():
    from setuhq.config import build_reviewers
    from setuhq.panel import standard_probes

    toml = tomllib.loads((ROOT / "configs" / "sweep.toml").read_text())["reviewers"]
    assert standard_probes() == toml
    first = standard_probes()
    first[0]["seed"] = 0
    assert standard_probes()[0]["seed"] == 11, "each call returns fresh copies"
    assert [r.reviewer_id for r in build_reviewers(standard_probes())] == [r["id"] for r in toml]


def test_the_wheel_ships_the_calibrated_weights_and_uses_them_without_a_checkout(tmp_path, monkeypatch):
    from setuhq import cli, panel
    from setuhq.config import load_config

    shipped = panel.packaged_weights_path()
    assert shipped and shipped.read_bytes() == (ROOT / "docs/results/reviewer_weights_full_panel.json").read_bytes()
    assert shipped.with_name("reviewer_weights_full_panel.calibration.json").is_file()
    cfg = load_config(ROOT / "configs" / "sweep.toml")
    monkeypatch.chdir(tmp_path)  # no docs/ here: an installed package
    assert panel.default_weights_path() == str(shipped)
    weights, source = cli.resolve_weights(cfg, None)
    assert weights == {k: v for k, v in json.loads(shipped.read_text()).items() if k.startswith("volunteer")}
    assert str(shipped) in source and "uniform" not in source
    from setuhq.starsearch import panel_weights

    w, src = panel_weights(cfg)
    assert w["volunteer-cautious"] == 0.4 and "uniform" not in src
    assert panel.default_weights()["volunteer-sensitive"] == 0.6


def test_check_dist_expects_the_weights():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_dist", ROOT / "scripts" / "check_dist.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "setuhq/data/reviewer_weights_full_panel.json" in mod.WHEEL_REQUIRED


KEY = "sk-test-0123456789abcdefABCDEF"


def _reply(captured):
    def transport(url, headers, body, timeout):
        captured.append((url, headers))
        return {"choices": [{"message": {"content": '{"marks": []}'}, "finish_reason": "stop"}], "model": "m"}
    return transport


@pytest.mark.parametrize("env", [None, "ENVKEY-0123456789"])
def test_an_openai_key_passed_per_call_wins_and_the_environment_stays_the_fallback(monkeypatch, env):
    from setuhq.reviewers.openai_compat import OpenAIReviewer

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    if env:
        monkeypatch.setenv("OPENAI_API_KEY", env)
    cap: list = []
    r = OpenAIReviewer("s", model="m", api_key=KEY, transport=_reply(cap))
    assert r.available()
    r.backend.call("sys", "user", _png())
    assert cap[-1][1]["Authorization"] == f"Bearer {KEY}"
    plain = OpenAIReviewer("s2", model="m", transport=_reply(cap))
    assert plain.available() is bool(env)
    if env:
        plain.backend.call("sys", "user", _png())
        assert cap[-1][1]["Authorization"] == f"Bearer {env}"


def test_a_passed_key_never_shows(monkeypatch, caplog):
    from setuhq.reviewers.claude import ClaudeReviewer
    from setuhq.reviewers.gemini import GeminiReviewer
    from setuhq.reviewers.openai_compat import OpenAICompatibleReviewer
    from setuhq.reviewers.sentinel import Secret

    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    revs = [ClaudeReviewer("c", api_key=KEY, client=object()), GeminiReviewer("g", model="m", api_key=KEY),
            OpenAICompatibleReviewer("o", model="m", base_url="https://example.org/v1", api_key=Secret(KEY))]
    for r in revs:
        text = repr(vars(r.backend)) + str(vars(r.backend)) + json.dumps(r.describe()) + repr(r.backend._key)
        assert KEY not in text
        with pytest.raises(TypeError):
            pickle.dumps(r.backend._key)
    assert revs[1].available() and revs[2].available()
    assert KEY not in caplog.text
    with pytest.raises(ValueError):  # a key in the URL is refused, even one passed in code
        OpenAICompatibleReviewer("o", model="m", base_url=f"https://example.org/v1?x={KEY}", api_key=KEY)


def test_a_config_file_still_never_holds_a_key():
    from setuhq.config import build_reviewers

    with pytest.raises(ValueError):
        build_reviewers([{"type": "openai", "id": "x", "model": "m", "api_key": KEY}])


def test_gemini_sends_the_passed_key(monkeypatch):
    from setuhq.reviewers.gemini import GeminiReviewer

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cap = []

    def transport(url, headers, body, timeout):
        cap.append(headers)
        return {"candidates": [{"content": {"parts": [{"text": '{"marks": []}'}]}, "finishReason": "STOP"}]}
    GeminiReviewer("g", model="m", api_key=KEY, transport=transport).backend.call("s", "u", _png())
    assert cap[0]["x-goog-api-key"] == KEY


def _png() -> Path:
    import tempfile

    p = Path(tempfile.mkdtemp()) / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")
    return p

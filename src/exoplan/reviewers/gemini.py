"""A Sentinel on Google Gemini (the Gemini API's ``generateContent``, with the PNG inline).

Key from ``GEMINI_API_KEY``, sent in the ``x-goog-api-key`` header (never in the URL). Plain
HTTPS through the standard library (:mod:`exoplan.reviewers.http`): no SDK to install. The
model id recorded with each review is the answer's ``modelVersion``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from urllib.parse import quote

from exoplan.reviewers.http import Transport, check_endpoint, post_json, redact
from exoplan.reviewers.sentinel import KEY_ENV, RefusalError, Reply, SentinelReviewer
from exoplan.reviewers.task import ReviewError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# finishReason values that mean the provider withheld the answer: a refusal, not a malformed reply.
BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


class GeminiBackend:
    provider = "gemini"

    def __init__(self, model: str, *, base_url: str = GEMINI_BASE_URL, max_tokens: int = 8192,
                 timeout: float = 120.0, transport: Transport | None = None):
        if not model:
            raise ValueError("a gemini Sentinel needs a 'model' (a vision model id)")
        check_endpoint(base_url)
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.transport = transport

    def missing(self) -> str | None:
        return None if os.environ.get(KEY_ENV["gemini"]) else f"{KEY_ENV['gemini']} is not set"

    def cache_tag(self) -> str:
        return self.provider

    def prompt_parts(self, system: str, user: str, image: Path) -> list[str]:
        return [system, user]

    def body(self, system: str, user: str, image: Path) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [
                {"text": user},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image.read_bytes()).decode("ascii")}},
            ]}],
            # Thinking models spend output tokens before answering, so the budget is generous.
            "generationConfig": {"maxOutputTokens": self.max_tokens, "responseMimeType": "application/json"},
        }

    def call(self, system: str, user: str, image: Path) -> Reply:
        send = self.transport or post_json
        url = f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent"
        data = send(url, {"x-goog-api-key": os.environ.get(KEY_ENV["gemini"], "")}, self.body(system, user, image),
                    self.timeout)
        return parse_generate_content(data)


def parse_generate_content(data: dict) -> Reply:
    """The text and reported model of a ``generateContent`` answer; blocks raise :class:`RefusalError`."""
    if not isinstance(data, dict):
        raise ReviewError("gemini: the answer is not a JSON object")
    if data.get("error"):
        err = data["error"]
        raise ReviewError(redact(f"gemini: {err.get('message', err) if isinstance(err, dict) else err}")[:300])
    feedback = data.get("promptFeedback") or {}
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        raise RefusalError(f"gemini: the prompt was blocked ({feedback['blockReason']})")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise ReviewError("gemini: no candidates in the answer")
    first = candidates[0]
    if first.get("finishReason") in BLOCKED:
        raise RefusalError(f"gemini: the answer was withheld (finishReason {first['finishReason']})")
    parts = (first.get("content") or {}).get("parts") if isinstance(first.get("content"), dict) else None
    text = "".join(p.get("text", "") for p in parts or [] if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        raise ReviewError(f"gemini: empty answer (finishReason {first.get('finishReason')!r})")
    model = data.get("modelVersion")
    return Reply(text, model if isinstance(model, str) and model else None)


class GeminiReviewer(SentinelReviewer):
    """A Sentinel on Google Gemini. Config type ``gemini``; key from ``GEMINI_API_KEY``."""

    def __init__(self, reviewer_id: str, model: str = "", persona: str = "volunteer",
                 cache_dir: str | Path | None = None, max_tokens: int = 8192, retries: int = 3,
                 timeout: float = 120.0, base_url: str = GEMINI_BASE_URL, transport: Transport | None = None,
                 kind: str = "gemini"):
        super().__init__(reviewer_id, GeminiBackend(model, base_url=base_url, max_tokens=max_tokens, timeout=timeout,
                                                    transport=transport),
                         persona=persona, cache_dir=cache_dir, retries=retries, kind=kind)

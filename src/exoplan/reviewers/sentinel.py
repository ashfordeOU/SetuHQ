"""A Sentinel: one AI reviewer, on any provider, answering the same task in the same strict JSON.

The task, the persona prompts, the JSON schema, the validation and the clipping live in
:mod:`exoplan.reviewers.task` and are the same for every provider. A provider is a
*backend*: it takes the system prompt, the user text and the rendered PNG, and returns the
model's text and the model id the provider reports. The reviewer does the rest:

* **Cache.** One file per answer, keyed by the prompt version, the provider (and, for an
  OpenAI-compatible endpoint, its base URL), the model, the persona, the prompt and the
  image's SHA-256. The same plot sent to two providers or two models never shares an answer.
* **Retries.** A malformed answer, an answer in the wrong schema, a timeout or an HTTP error
  is retried with backoff, then reported as :class:`ReviewError`; the pipeline skips that one
  review and says so. A refusal is not retried: asking again rarely changes it and costs money.
* **Provenance.** Every classification carries ``provider``, ``model`` (the exact id the API
  reported, else the configured one, with ``model_reported`` saying which), ``called_at``
  (UTC, when the provider answered; kept in the cache so a cached answer keeps its time),
  ``prompt_version``, ``persona`` and ``cached``.

Keys are read from the environment only, one variable per provider (:data:`KEY_ENV`); they
are never written to the cache, the manifest or an error message.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from exoplan.reviewers.base import Classification
from exoplan.reviewers.task import PROMPT_VERSION, ReviewError, build_prompt, parse_response
from exoplan.subjects import Subject

# The environment variable each provider's key is read from. An OpenAI-compatible endpoint
# names its own (``api_key_env``), or none for a local server such as Ollama.
KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# How the pages and the manifest name each provider. Keys are the provider ids recorded per review.
PROVIDER_LABELS = {
    "anthropic": "Anthropic API (Claude)",
    "claude-code": "Claude Code CLI (Claude, Anthropic)",
    "openai": "OpenAI API",
    "gemini": "Google Gemini API",
    "openai-compatible": "OpenAI-compatible endpoint",
}


class RefusalError(ReviewError):
    """The provider declined to answer (a refusal or a safety block). Not retried."""


@dataclass(frozen=True)
class Reply:
    """What a backend returns: the model's text and the model id the provider reported (None if it did not)."""

    text: str
    model: str | None = None


class Backend(Protocol):
    provider: str
    model: str | None

    def missing(self) -> str | None:
        """Why this backend cannot run here (no key, no SDK, no CLI), or None when it can."""

    def cache_tag(self) -> str:
        """The provider part of the cache key: the provider id, plus the endpoint where that matters."""

    def prompt_parts(self, system: str, user: str, image: Path) -> list[str]:
        """The exact prompt text the provider receives, for the cache key."""

    def call(self, system: str, user: str, image: Path) -> Reply: ...


class _Unbounded:
    """Unbounded stand-in so an answer can be shape-checked before it is cached."""

    start = float("-inf")
    end = float("inf")
    subject_id = "shape-check"


def check_shape(text: str, reviewer_id: str) -> None:
    """Raise :class:`ReviewError` unless the text holds a usable answer in the strict schema."""
    parse_response(text, _Unbounded(), reviewer_id)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SentinelReviewer:
    """An AI reviewer on one backend. ``kind`` is the config type (``claude``, ``openai``, ...)."""

    def __init__(self, reviewer_id: str, backend: Backend, *, persona: str = "volunteer",
                 cache_dir: str | Path | None = None, retries: int = 3, kind: str = "sentinel"):
        self.reviewer_id = reviewer_id
        self.backend = backend
        self.persona = persona
        self.cache_dir = cache_dir
        self.retries = retries
        self.kind = kind

    # -- availability and provenance -------------------------------------------------

    @property
    def provider(self) -> str:
        return self.backend.provider

    @property
    def model(self) -> str | None:
        return self.backend.model

    def available(self) -> bool:
        return self.backend.missing() is None

    def unavailable_reason(self) -> str | None:
        return self.backend.missing()

    def describe(self) -> dict:
        """Provider, configured model and persona, for the manifest. Never holds a key."""
        out = {"provider": self.provider, "provider_label": PROVIDER_LABELS.get(self.provider, self.provider),
               "model": self.model or "default", "persona": self.persona, "prompt_version": PROMPT_VERSION}
        endpoint = getattr(self.backend, "base_url", None)
        if endpoint and self.provider == "openai-compatible":
            out["endpoint"] = endpoint
        return out

    # -- the review ------------------------------------------------------------------

    def cache_key(self, system: str, user: str, image: Path, image_bytes: bytes) -> str:
        fields = [PROMPT_VERSION, self.backend.cache_tag(), self.model or "default", self.persona,
                  *self.backend.prompt_parts(system, user, image)]
        return hashlib.sha256("\x1f".join(fields).encode() + hashlib.sha256(image_bytes).digest()).hexdigest()

    def review(self, subject: Subject, image_path: str | Path | None = None) -> Classification:
        if image_path is None:
            raise ValueError(f"{type(self).__name__} needs the rendered subject image")
        image = Path(image_path).resolve()
        image_bytes = image.read_bytes()
        system, user = build_prompt(subject, self.persona)
        key = self.cache_key(system, user, image, image_bytes)
        cached = None if self.cache_dir is None else Path(self.cache_dir) / f"{key}.json"
        if cached is not None and cached.exists():
            entry = json.loads(cached.read_text())
            hit = True
        else:
            reply = self._call(system, user, image)
            entry = {"provider": self.provider, "model_requested": self.model, "model_reported": reply.model,
                     "called_at": now_utc(), "prompt_version": PROMPT_VERSION, "text": reply.text}
            hit = False
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps(entry))
        result = parse_response(entry["text"], subject, self.reviewer_id)
        reported = entry.get("model_reported")
        meta = {
            "provider": entry.get("provider") or self.provider,
            "model": reported or self.model or "default",
            "model_reported": bool(reported),
            "called_at": entry.get("called_at"),  # None for an answer cached before called_at was recorded
            "prompt_version": entry.get("prompt_version") or PROMPT_VERSION,
            "persona": self.persona,
            "cached": hit,
        }
        if self.provider == "openai-compatible":
            meta["endpoint"] = getattr(self.backend, "base_url", None)
        return Classification(result.reviewer_id, result.subject_id, result.label, result.marks, result.reason,
                              result.confidence, result.rationale, meta)

    def _call(self, system: str, user: str, image: Path) -> Reply:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                reply = self.backend.call(system, user, image)
                check_shape(reply.text, self.reviewer_id)
                return reply
            except RefusalError:
                raise
            except Exception as exc:  # malformed answers, wrong schema, timeouts and HTTP errors are retried
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(2**attempt)
        raise ReviewError(f"{self.reviewer_id}: no usable answer after {self.retries} attempts: {last_error}")

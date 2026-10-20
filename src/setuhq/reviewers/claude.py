"""Claude as a reviewer through the Anthropic API (vision), the default Sentinel provider.

The task, the prompt, the strict JSON schema, validation and clipping are shared by every
provider (:mod:`setuhq.reviewers.task`, re-exported here). Caching, retries and the
provenance of every answer are in :class:`setuhq.reviewers.sentinel.SentinelReviewer`.

The reviewer is inactive unless ``ANTHROPIC_API_KEY`` is set (and the ``anthropic`` package is
installed: ``pip install -e '.[claude]'``) or a client is passed in. ``available()`` says which,
and the pipeline records skipped reviewers, with the reason, in the run manifest.
"""

from __future__ import annotations

import base64
import importlib.util
import os
import time  # noqa: F401  (tests patch setuhq.reviewers.claude.time.sleep to skip the backoff)
from pathlib import Path

from setuhq.reviewers.http import ProviderRejected, redact
from setuhq.reviewers.sentinel import KEY_ENV, RefusalError, Reply, SentinelReviewer
from setuhq.reviewers.task import (  # noqa: F401  (the shared task, re-exported for existing imports)
    OUTPUT_SCHEMA,
    PERSONAS,
    PROMPT_VERSION,
    VOLUNTEER_TASK,
    ReviewError,
    build_prompt,
    fatal_status,
    parse_response,
)

DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicBackend:
    """The Anthropic Messages API, with the PNG as a base64 image block."""

    provider = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, *, max_tokens: int = 1024, client: object | None = None):
        self.model = model
        self.max_tokens = max_tokens
        self.client = client

    def missing(self) -> str | None:
        if self.client is not None:
            return None
        if not os.environ.get(KEY_ENV["anthropic"]):
            return f"{KEY_ENV['anthropic']} is not set"
        if importlib.util.find_spec("anthropic") is None:
            return "the anthropic package is not installed (pip install -e '.[claude]')"
        return None

    def cache_tag(self) -> str:
        return self.provider

    def prompt_parts(self, system: str, user: str, image: Path) -> list[str]:
        return [system, user]

    def call(self, system: str, user: str, image: Path) -> Reply:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()
        image_block = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                   "data": base64.b64encode(image.read_bytes()).decode("ascii")}}
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": [image_block, {"type": "text", "text": user}]}],
            )
        except Exception as exc:  # the SDK's errors carry status_code: a bad key or model is not retried
            if fatal_status(getattr(exc, "status_code", None)):
                raise ProviderRejected(redact(f"anthropic: HTTP {exc.status_code}: {exc}",
                                              [os.environ.get(KEY_ENV["anthropic"], "")])[:300]) from None
            raise
        if getattr(response, "stop_reason", None) == "refusal":
            raise RefusalError("anthropic: the model declined to answer (stop_reason 'refusal')")
        text = next((block.text for block in response.content if getattr(block, "type", "") == "text"), None)
        if text is None:
            raise ReviewError("anthropic: no text block in the response")
        reported = getattr(response, "model", None)
        return Reply(text, reported if isinstance(reported, str) else None)


class ClaudeReviewer(SentinelReviewer):
    """A Sentinel on the Anthropic API. Config type ``claude``."""

    def __init__(self, reviewer_id: str, model: str = DEFAULT_MODEL, persona: str = "volunteer",
                 cache_dir: str | Path | None = None, max_tokens: int = 1024, retries: int = 3,
                 client: object | None = None, kind: str = "claude"):
        super().__init__(reviewer_id, AnthropicBackend(model, max_tokens=max_tokens, client=client),
                         persona=persona, cache_dir=cache_dir, retries=retries, kind=kind)

    @property
    def client(self):
        return self.backend.client

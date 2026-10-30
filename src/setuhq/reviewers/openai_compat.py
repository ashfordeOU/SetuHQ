# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Sentinels on OpenAI and on any OpenAI-compatible endpoint (Chat Completions with image input).

* ``openai``: the OpenAI API, ``https://api.openai.com/v1``, key from ``OPENAI_API_KEY``.
* ``openai_compatible``: any server that speaks Chat Completions, set by ``base_url``: Ollama
  (``http://localhost:11434/v1``), vLLM, LM Studio, OpenRouter, Azure OpenAI (``auth = "api-key"``)
  and similar. Its key, if it needs one, is read from the variable named by ``api_key_env``.

Plain HTTPS through the standard library (:mod:`setuhq.reviewers.http`): no SDK to install.
The model must be a vision model; the plot is sent as a ``data:image/png;base64`` URL.
The model id recorded with each review is the ``model`` field of the provider's answer.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from setuhq.reviewers.http import Transport, check_endpoint, post_json, redact
from setuhq.reviewers.sentinel import KEY_ENV, RefusalError, Reply, SentinelReviewer, as_secret, key_value
from setuhq.reviewers.task import ReviewError

OPENAI_BASE_URL = "https://api.openai.com/v1"


class ChatCompletionsBackend:
    """One Chat Completions endpoint. ``provider`` is ``openai`` or ``openai-compatible``."""

    def __init__(self, *, provider: str, model: str, base_url: str, api_key_env: str | None,
                 auth: str = "bearer", query: dict | None = None, max_tokens: int = 4096,
                 json_mode: bool = False, timeout: float = 120.0, transport: Transport | None = None,
                 api_key: str | None = None):
        if not model:
            raise ValueError(f"a {provider} Sentinel needs a 'model' (a vision model id)")
        if not base_url:
            raise ValueError(f"a {provider} Sentinel needs a 'base_url'")
        if auth not in ("bearer", "api-key", "none"):
            raise ValueError(f"auth must be 'bearer', 'api-key' or 'none', not {auth!r}")
        # no key in the URL or the query: from the environment, or passed in code (api_key)
        check_endpoint(base_url, query, api_key_env, extra_keys=[api_key] if api_key else ())
        self._key = as_secret(api_key)
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.auth = auth
        self.query = dict(query or {})
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.timeout = timeout
        self.transport = transport

    def missing(self) -> str | None:
        if self.auth != "none" and self._key is None and self.api_key_env and not os.environ.get(self.api_key_env):
            return f"{self.api_key_env} is not set"
        return None

    def cache_tag(self) -> str:
        # Two endpoints can serve different weights under one model name, so the endpoint is part of the key.
        return self.provider if self.provider == "openai" else f"{self.provider}@{self.base_url}"

    def prompt_parts(self, system: str, user: str, image: Path) -> list[str]:
        return [system, user]

    def _headers(self) -> dict:
        key = key_value(self._key, self.api_key_env)
        if not key or self.auth == "none":
            return {}
        return {"api-key": key} if self.auth == "api-key" else {"Authorization": f"Bearer {key}"}

    def _url(self) -> str:
        url = f"{self.base_url}/chat/completions"
        if self.query:
            from urllib.parse import urlencode

            url += "?" + urlencode(self.query)
        return url

    def body(self, system: str, user: str, image: Path) -> dict:
        data_url = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [{"type": "text", "text": user},
                                             {"type": "image_url", "image_url": {"url": data_url}}]},
            ],
        }
        # OpenAI's current models take max_completion_tokens; most compatible servers still read max_tokens.
        body["max_completion_tokens" if self.provider == "openai" else "max_tokens"] = self.max_tokens
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def call(self, system: str, user: str, image: Path) -> Reply:
        send = self.transport or post_json
        data = send(self._url(), self._headers(), self.body(system, user, image), self.timeout)
        return parse_chat_completion(data, self.provider)


def parse_chat_completion(data: dict, provider: str) -> Reply:
    """The text and reported model of a Chat Completions answer; refusals and errors raise."""
    if not isinstance(data, dict):
        raise ReviewError(f"{provider}: the answer is not a JSON object")
    if data.get("error"):
        err = data["error"]
        raise ReviewError(redact(f"{provider}: {err.get('message', err) if isinstance(err, dict) else err}")[:300])
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ReviewError(f"{provider}: no choices in the answer")
    choice = choices[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    if message.get("refusal"):
        raise RefusalError(f"{provider}: the model declined to answer: {str(message['refusal'])[:200]}")
    if choice.get("finish_reason") == "content_filter":
        raise RefusalError(f"{provider}: the answer was withheld by the provider's content filter")
    content = message.get("content")
    if isinstance(content, list):  # some servers return content parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise ReviewError(f"{provider}: empty answer (finish_reason {choice.get('finish_reason')!r})")
    model = data.get("model")
    return Reply(content, model if isinstance(model, str) and model else None)


class OpenAIReviewer(SentinelReviewer):
    """A Sentinel on the OpenAI API. Config type ``openai``; key from ``OPENAI_API_KEY``."""

    def __init__(self, reviewer_id: str, model: str = "", persona: str = "volunteer",
                 cache_dir: str | Path | None = None, max_tokens: int = 4096, retries: int = 3,
                 timeout: float = 120.0, base_url: str = OPENAI_BASE_URL, transport: Transport | None = None,
                 kind: str = "openai", api_key: str | None = None):
        backend = ChatCompletionsBackend(provider="openai", model=model, base_url=base_url, api_key_env=KEY_ENV["openai"],
                                         max_tokens=max_tokens, json_mode=True, timeout=timeout, transport=transport,
                                         api_key=api_key)
        super().__init__(reviewer_id, backend, persona=persona, cache_dir=cache_dir, retries=retries, kind=kind)


class OpenAICompatibleReviewer(SentinelReviewer):
    """A Sentinel on any OpenAI-compatible endpoint. Config type ``openai_compatible``."""

    def __init__(self, reviewer_id: str, model: str = "", base_url: str = "", api_key_env: str | None = None,
                 auth: str = "bearer", query: dict | None = None, persona: str = "volunteer",
                 cache_dir: str | Path | None = None, max_tokens: int = 4096, json_mode: bool = False,
                 retries: int = 3, timeout: float = 300.0, transport: Transport | None = None,
                 kind: str = "openai_compatible", api_key: str | None = None):
        backend = ChatCompletionsBackend(provider="openai-compatible", model=model, base_url=base_url,
                                         api_key_env=api_key_env, auth=auth if (api_key_env or api_key) else "none", query=query,
                                         max_tokens=max_tokens, json_mode=json_mode, timeout=timeout, transport=transport,
                                         api_key=api_key)
        super().__init__(reviewer_id, backend, persona=persona, cache_dir=cache_dir, retries=retries, kind=kind)

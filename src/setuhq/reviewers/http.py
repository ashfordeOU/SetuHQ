# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Plain HTTPS JSON POST for the Sentinel providers that need no SDK (OpenAI, Gemini, OpenAI-compatible).

The standard library only, so no extra package is needed. A backend takes a ``transport``
callable with the same signature as :func:`post_json`; tests pass a fake and never touch the network.

Keys stay out of every message: errors never echo request headers, the provider's error body is
redacted (bearer tokens, key-like strings and the request's own key values) before it is quoted, and
:func:`check_endpoint` refuses a base URL or query that carries a credential, so none can reach the
cache, the manifest or a log.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from setuhq.reviewers.task import NotRetried, ReviewError, fatal_status

Transport = Callable[[str, dict, dict, float], dict]

# Query parameters that carry a credential; refused in a config (compared case-insensitively).
CREDENTIAL_PARAMS = {"key", "api-key", "api_key", "apikey", "x-api-key", "token", "access_token", "sig", "signature",
                     "code", "secret", "client_secret", "password", "subscription-key", "authorization", "access-key",
                     "access_key"}
# The provider key variables; a query value or URL equal to one of their values is refused.
PROVIDER_KEY_ENVS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
# A path segment this long in these characters looks like a token, not a route.
_TOKENLIKE_SEGMENT = re.compile(r"[A-Za-z0-9_\-+=]{24,}")
_KEYLIKE = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_\-+/=]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)((?:api[_-]?key|key|token|secret|password|signature|sig)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}]+"),
]


class ProviderTimeout(ReviewError):
    """The provider did not answer in time. Retried by the reviewer."""


class ProviderRejected(NotRetried):
    """The provider refused the request itself (401, 403, 404, 400 ...): a bad key or a bad model. Not retried."""


def redact(text: str, secrets=()) -> str:
    """``text`` with bearer tokens, key-like strings and each of ``secrets`` replaced by [redacted]."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            for form in _encodings(secret):
                text = text.replace(form, "[redacted]")
    for pattern in _KEYLIKE:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[redacted]", text)
    return text


def _encodings(secret: str) -> list[str]:
    """The secret as it is and base64-encoded (standard and URL-safe, with and without padding), longest first."""
    raw = secret.encode()
    forms = {secret}
    for enc in (base64.b64encode(raw), base64.urlsafe_b64encode(raw)):
        forms |= {enc.decode(), enc.decode().rstrip("=")}
    return sorted(forms, key=len, reverse=True)


def _secrets(headers: dict) -> list[str]:
    out = []
    for value in headers.values():
        value = str(value)
        out.append(value)
        if value.lower().startswith("bearer "):
            out.append(value[7:])
    return out


def safe_url(url: str | None) -> str | None:
    """What is recorded of an endpoint: scheme, host and port only, plus a hash of everything after them (path,
    query), so two endpoints can be told apart without a path or a query ever reaching a record. None stays None."""
    if not url:
        return url
    parts = urlsplit(url)
    origin = urlunsplit((parts.scheme, (parts.hostname or "") + (f":{parts.port}" if parts.port else ""), "", "", ""))
    rest = parts.path.rstrip("/") + (f"?{parts.query}" if parts.query else "")
    return origin if not rest else f"{origin} [path sha256:{hashlib.sha256(rest.encode()).hexdigest()[:12]}]"


def check_endpoint(base_url: str, query: dict | None = None, key_env: str | None = None) -> None:
    """Refuse an endpoint that could carry a credential: a user:password part, a fragment, a ;param, a path
    segment that looks like a token, a credential-named query parameter, or any query value or URL part equal to
    a provider key that is set (``PROVIDER_KEY_ENVS`` and ``key_env``). The message never echoes the value."""
    from urllib.parse import parse_qsl

    parts = urlsplit(base_url)
    if parts.username is not None or parts.password is not None:
        raise ValueError("base_url must not carry credentials (user:password@); name the key's variable with api_key_env")
    if parts.scheme not in ("http", "https"):
        raise ValueError("base_url must be an http or https URL")
    if parts.fragment or "#" in base_url:
        raise ValueError("base_url must not have a #fragment")
    if ";" in parts.path:
        raise ValueError("base_url must not have ;parameters in its path")
    if any(_TOKENLIKE_SEGMENT.fullmatch(seg) for seg in parts.path.split("/")):
        raise ValueError("base_url has a path segment that looks like a token (24 or more key-like characters); "
                         "keys are read from the environment only (api_key_env)")
    pairs = [(str(k), str(v)) for k, v in (query or {}).items()] + parse_qsl(parts.query, keep_blank_values=True)
    bad = sorted({k.lower() for k, _ in pairs} & CREDENTIAL_PARAMS)
    if bad:
        raise ValueError(f"query parameter(s) {', '.join(bad)} look like a credential; keys are read from the "
                         "environment only (api_key_env)")
    keys = [os.environ.get(v, "") for v in (*PROVIDER_KEY_ENVS, *([key_env] if key_env else []))]
    keys = [k for k in keys if len(k) >= 4]
    if any(v == k or k in v for _, v in pairs for k in keys) or any(k in base_url for k in keys):
        raise ValueError("base_url or query holds the value of a provider key; keys are read from the environment only")


def post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    """POST ``body`` as JSON and return the decoded JSON answer. Raises :class:`ReviewError` on any failure:
    :class:`ProviderRejected` (not retried) for a 4xx other than 408 and 429."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https URL from config)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", "replace") if exc.fp is not None else ""
        message = f"HTTP {exc.code} from {_host(url)}: {redact(detail, _secrets(headers))[:300]}"
        raise (ProviderRejected if fatal_status(exc.code) else ReviewError)(message) from None
    except (socket.timeout, TimeoutError) as exc:
        raise ProviderTimeout(f"timed out after {timeout:.0f} s waiting for {_host(url)}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise ProviderTimeout(f"timed out after {timeout:.0f} s waiting for {_host(url)}") from exc
        raise ReviewError(f"cannot reach {_host(url)}: {redact(str(exc.reason), _secrets(headers))}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{_host(url)} did not answer with JSON") from exc
    if not isinstance(data, dict):
        raise ReviewError(f"{_host(url)} answered with JSON that is not an object")
    return data


def _host(url: str) -> str:
    """The scheme and host of a URL, without credentials, path or query (which may carry a deployment or a version)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname or ''}{f':{parts.port}' if parts.port else ''}"

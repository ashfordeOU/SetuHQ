"""Plain HTTPS JSON POST for the Sentinel providers that need no SDK (OpenAI, Gemini, OpenAI-compatible).

The standard library only, so no extra package is needed. A backend takes a ``transport``
callable with the same signature as :func:`post_json`; tests pass a fake and never touch the network.

Keys stay out of every message: errors never echo request headers, the provider's error body is
redacted (bearer tokens, key-like strings and the request's own key values) before it is quoted, and
:func:`check_endpoint` refuses a base URL or query that carries a credential, so none can reach the
cache, the manifest or a log.
"""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from exoplan.reviewers.task import NotRetried, ReviewError, fatal_status

Transport = Callable[[str, dict, dict, float], dict]

# Query parameters that carry a credential; refused in a config (compared case-insensitively).
CREDENTIAL_PARAMS = {"key", "api-key", "api_key", "apikey", "token", "access_token", "sig", "signature", "code",
                     "secret", "password"}
_KEYLIKE = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
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
            text = text.replace(secret, "[redacted]")
    for pattern in _KEYLIKE:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[redacted]", text)
    return text


def _secrets(headers: dict) -> list[str]:
    out = []
    for value in headers.values():
        value = str(value)
        out.append(value)
        if value.lower().startswith("bearer "):
            out.append(value[7:])
    return out


def safe_url(url: str | None) -> str | None:
    """The URL without any user:password part (what is recorded), or None."""
    if not url:
        return url
    parts = urlsplit(url)
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    netloc = host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def check_endpoint(base_url: str, query: dict | None = None) -> None:
    """Refuse a base URL with a user:password part, or a query holding a credential. The message never echoes it."""
    parts = urlsplit(base_url)
    if parts.username is not None or parts.password is not None:
        raise ValueError("base_url must not carry credentials (user:password@); name the key's variable with api_key_env")
    if parts.scheme not in ("http", "https"):
        raise ValueError("base_url must be an http or https URL")
    from urllib.parse import parse_qsl

    names = {k.lower() for k in (query or {})} | {k.lower() for k, _ in parse_qsl(parts.query)}
    bad = sorted(names & CREDENTIAL_PARAMS)
    if bad:
        raise ValueError(f"query parameter(s) {', '.join(bad)} look like a credential; keys are read from the "
                         "environment only (api_key_env)")


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

"""Plain HTTPS JSON POST for the Sentinel providers that need no SDK (OpenAI, Gemini, OpenAI-compatible).

The standard library only, so no extra package is needed. A backend takes a ``transport``
callable with the same signature as :func:`post_json`; tests pass a fake and never touch the network.
Errors never echo request headers, so a key cannot leak into a log, a warning or the manifest.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Callable

from exoplan.reviewers.task import ReviewError

Transport = Callable[[str, dict, dict, float], dict]


class ProviderTimeout(ReviewError):
    """The provider did not answer in time. Retried by the reviewer."""


def post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    """POST ``body`` as JSON and return the decoded JSON answer. Raises :class:`ReviewError` on any failure."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https URL from config)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace") if exc.fp is not None else ""
        raise ReviewError(f"HTTP {exc.code} from {_host(url)}: {detail}") from None
    except (socket.timeout, TimeoutError) as exc:
        raise ProviderTimeout(f"timed out after {timeout:.0f} s waiting for {_host(url)}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise ProviderTimeout(f"timed out after {timeout:.0f} s waiting for {_host(url)}") from exc
        raise ReviewError(f"cannot reach {_host(url)}: {exc.reason}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{_host(url)} did not answer with JSON") from exc
    if not isinstance(data, dict):
        raise ReviewError(f"{_host(url)} answered with JSON that is not an object")
    return data


def _host(url: str) -> str:
    """The scheme and host of a URL, without its path or query (which may carry a deployment or a version)."""
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname or ''}{f':{parts.port}' if parts.port else ''}"

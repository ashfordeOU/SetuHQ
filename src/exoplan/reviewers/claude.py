"""Claude as a reviewer: the same task, given to a vision-capable model.

Each review sends the blind-coded PNG plot and the volunteer instructions, and
asks for strict JSON. The response is validated and clipped to the subject's
time range, so a malformed or out-of-range answer cannot create a candidate.

Responses are cached on disk, keyed by a hash of the model, prompt version,
prompt and image. Repeating a run therefore costs nothing and gives the same
panel output. Two personas (``volunteer`` and ``skeptic``) provide different
viewpoints, like different volunteers would.

The reviewer is inactive unless ``ANTHROPIC_API_KEY`` is set or a client is
passed in. ``available()`` says which, and the pipeline records skipped
reviewers in the run manifest.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from exoplan.reviewers.base import LABELS, NOISE_REASONS, Classification, Mark
from exoplan.subjects import Subject

PROMPT_VERSION = "2026-10-16.1"

VOLUNTEER_TASK = (
    "Inspect the star brightness plot for dips that could signal a transit. "
    "Mark the start and end of each such dip, then classify the subject as "
    "'potential_planet' (at least one dip looks like a transit) or 'noise'."
)

PERSONAS = {
    "volunteer": (
        "You are a careful citizen-science volunteer. Mark dips that look like "
        "transits: a short, reproducible drop in brightness lasting minutes to hours, "
        "with a clear start and end. Single outlier points are not dips."
    ),
    "skeptic": (
        "You are a strict reviewer. Mark only dips that look like transits, and "
        "favour rejecting candidates that show eclipsing-binary signatures "
        "(V-shaped or rounded secondary dips), stellar variability ramps, or "
        "instrumental steps. When unsure, label 'noise' and give the reason."
    ),
}

OUTPUT_SCHEMA = (
    '{"marks": [{"start": <number>, "end": <number>}], '
    '"label": "potential_planet" | "noise", '
    '"noise_reason": null | "eclipsing_binary" | "stellar_variability" | "instrumental" | "other", '
    '"confidence": <number between 0 and 1>, "rationale": "<one or two sentences>"}'
)

_JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class ReviewError(RuntimeError):
    """Raised when the model's answer cannot be used after all retries."""


def build_prompt(subject: Subject, persona: str) -> tuple[str, str]:
    """Return (system prompt, user text). The user text carries the axis range but never the target identity."""
    if persona not in PERSONAS:
        raise ValueError(f"unknown persona {persona!r}; choose from {sorted(PERSONAS)}")
    system = (
        f"{PERSONAS[persona]}\n\n"
        "Read the time values from the x-axis of the plot. Answer with JSON only, "
        f"exactly this shape, and no other text:\n{OUTPUT_SCHEMA}"
    )
    user = (
        f"{VOLUNTEER_TASK}\n\n"
        f"Subject {subject.subject_id}. The x-axis runs from {subject.start:.5f} to "
        f"{subject.end:.5f} ({subject.time_unit}). Mark times inside that range only."
    )
    return system, user


def parse_response(text: str, subject: Subject, reviewer_id: str) -> Classification:
    """Validate the model's JSON and turn it into a :class:`Classification`. Raises :class:`ReviewError` if unusable."""
    match = _JSON_PATTERN.search(text)
    if match is None:
        raise ReviewError("no JSON object in response")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ReviewError(f"invalid JSON: {exc}") from exc

    label = payload.get("label")
    if label not in LABELS:
        raise ReviewError(f"label {label!r} is not one of {LABELS}")
    reason = payload.get("noise_reason")
    if reason is not None and reason not in NOISE_REASONS:
        reason = "other"
    if label == "potential_planet":
        reason = None

    marks: list[Mark] = []
    for raw in payload.get("marks") or []:
        try:
            start = float(raw["start"])
            end = float(raw["end"])
        except (KeyError, TypeError, ValueError):
            continue
        start, end = max(start, subject.start), min(end, subject.end)
        if end > start:
            marks.append(Mark(start, end))

    try:
        confidence = float(min(1.0, max(0.0, payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    if label == "potential_planet" and not marks:
        label = "noise"
        reason = "other"

    return Classification(
        reviewer_id=reviewer_id,
        subject_id=subject.subject_id,
        label=label,
        marks=tuple(marks),
        reason=reason,
        confidence=confidence,
        rationale=str(payload.get("rationale", ""))[:500],
    )


@dataclass
class ClaudeReviewer:
    reviewer_id: str
    model: str = "claude-sonnet-5-5"
    persona: str = "volunteer"
    cache_dir: str | Path | None = None
    max_tokens: int = 1024
    retries: int = 3
    client: object | None = None
    kind: str = "claude"

    def available(self) -> bool:
        return self.client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _get_client(self):
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()
        return self.client

    def review(self, subject: Subject, image_path: str | Path | None = None) -> Classification:
        if image_path is None:
            raise ValueError("ClaudeReviewer needs the rendered subject image")
        image_bytes = Path(image_path).read_bytes()
        system, user = build_prompt(subject, self.persona)

        cache_key = hashlib.sha256(
            "\x1f".join([PROMPT_VERSION, self.model, self.persona, system, user]).encode()
            + hashlib.sha256(image_bytes).digest()
        ).hexdigest()
        cached = self._cache_path(cache_key)
        if cached is not None and cached.exists():
            text = json.loads(cached.read_text())["text"]
        else:
            text = self._call(system, user, image_bytes)
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps({"model": self.model, "text": text}))

        return parse_response(text, subject, self.reviewer_id)

    def _cache_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return Path(self.cache_dir) / f"{key}.json"

    def _call(self, system: str, user: str, image_bytes: bytes) -> str:
        client = self._get_client()
        image_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            },
        }
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": [image_block, {"type": "text", "text": user}]}],
                )
                text = next(block.text for block in response.content if getattr(block, "type", "") == "text")
                _check_shape(text, self.reviewer_id)
                return text
            except Exception as exc:  # malformed answers and API errors are both retried, then reported
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(2**attempt)
        raise ReviewError(f"{self.reviewer_id}: no usable answer after {self.retries} attempts: {last_error}")


class _ShapeCheckSubject:
    """Unbounded stand-in so a response can be shape-checked before it is cached."""

    start = float("-inf")
    end = float("inf")
    subject_id = "shape-check"


def _check_shape(text: str, reviewer_id: str) -> None:
    parse_response(text, _ShapeCheckSubject(), reviewer_id)

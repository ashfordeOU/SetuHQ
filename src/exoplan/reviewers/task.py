"""The Sentinel task, shared by every provider: the prompt, the strict JSON schema, validation and clipping.

Each review sends the blind-coded PNG plot and the volunteer instructions, and asks for strict
JSON. :func:`parse_response` validates the answer and clips every mark to the subject's time
range, so a malformed or out-of-range answer cannot create a candidate, whichever model wrote it.
Two personas (``volunteer`` and ``skeptic``) give different viewpoints, as different volunteers would.

The prompt version is recorded with every review and is part of every cache key.
"""

from __future__ import annotations

import json
import re

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


def _first_json_object(text: str) -> dict:
    """Return the first decodable JSON object with a 'label' key, scanning from each '{' in turn."""
    decoder = json.JSONDecoder()
    for start in (m.start() for m in re.finditer(r"\{", text)):
        try:
            candidate, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and "label" in candidate:
            return candidate
    raise ReviewError("no JSON object with a label in response")


def parse_response(text: str, subject: Subject, reviewer_id: str) -> Classification:
    """Validate the model's JSON and turn it into a :class:`Classification`. Raises :class:`ReviewError` if unusable."""
    payload = _first_json_object(text)

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

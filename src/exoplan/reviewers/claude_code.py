"""Claude as a reviewer through the Claude Code CLI, with no API key.

Claude Code signs in with a Claude team or individual subscription. This
reviewer runs ``claude -p`` in print mode, points it at the rendered PNG and
asks for the same JSON answer as :class:`exoplan.reviewers.claude.ClaudeReviewer`.
Parsing, validation, caching and the task wording are shared with that
reviewer, so the two backends answer the same question.

Requirements: the ``claude`` command is on PATH and is signed in
(``claude`` then ``/login``). The reviewer is unavailable otherwise, and the
pipeline records it as skipped.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from exoplan.reviewers.base import Classification
from exoplan.reviewers.claude import PROMPT_VERSION, ReviewError, build_prompt, parse_response
from exoplan.subjects import Subject

Runner = Callable[[list[str], str], str]


def _subprocess_runner(cmd: list[str], cwd: str) -> str:
    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)
    if completed.returncode != 0:
        raise ReviewError(f"claude exited with {completed.returncode}: {completed.stderr.strip()[:300]}")
    return completed.stdout


@dataclass
class ClaudeCodeReviewer:
    reviewer_id: str
    persona: str = "volunteer"
    model: str | None = None
    binary: str = "claude"
    cache_dir: str | Path | None = None
    retries: int = 3
    runner: Runner | None = None
    kind: str = "claude_code"

    def available(self) -> bool:
        return self.runner is not None or shutil.which(self.binary) is not None

    def review(self, subject: Subject, image_path: str | Path | None = None) -> Classification:
        if image_path is None:
            raise ValueError("ClaudeCodeReviewer needs the rendered subject image")
        image = Path(image_path).resolve()
        system, user = build_prompt(subject, self.persona)
        request = (
            f"{system}\n\n{user}\n\n"
            f"The plot is the PNG at this absolute path: {image}. "
            "Open it with the Read tool, look at it, then reply with only the JSON object."
        )

        image_bytes = image.read_bytes()
        key = hashlib.sha256(
            "\x1f".join([PROMPT_VERSION, "claude-code", self.model or "default", self.persona, request]).encode()
            + hashlib.sha256(image_bytes).digest()
        ).hexdigest()
        cached = None if self.cache_dir is None else Path(self.cache_dir) / f"{key}.json"
        if cached is not None and cached.exists():
            text = json.loads(cached.read_text())["text"]
        else:
            text = self._call(request, image.parent, subject)
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps({"backend": "claude-code", "text": text}))
        return parse_response(text, subject, self.reviewer_id)

    def _command(self, request: str) -> list[str]:
        cmd = [self.binary, "-p", request, "--output-format", "json", "--allowedTools", "Read"]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def _call(self, request: str, cwd: Path, subject: Subject) -> str:
        run = self.runner or _subprocess_runner
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                stdout = run(self._command(request), str(cwd))
                envelope = json.loads(stdout)
                text = envelope.get("result", "") if isinstance(envelope, dict) else str(envelope)
                parse_response(text, _ShapeCheck(), self.reviewer_id)
                return text
            except Exception as exc:  # malformed output and CLI errors are retried, then reported
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(2**attempt)
        raise ReviewError(f"{self.reviewer_id}: no usable answer after {self.retries} attempts: {last_error}")


class _ShapeCheck:
    start = float("-inf")
    end = float("inf")
    subject_id = "shape-check"

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Claude as a reviewer through the Claude Code CLI, with no API key.

Claude Code signs in with a Claude team or individual subscription. This
reviewer runs ``claude -p`` in print mode, points it at the rendered PNG and
asks for the same JSON answer as every other Sentinel. Parsing, validation,
caching, provenance and the task wording are shared
(:class:`setuhq.reviewers.sentinel.SentinelReviewer`), so every backend answers the same question.

The model id is read from the CLI's JSON envelope (``modelUsage``: the model that
wrote the most output tokens) and recorded with the review; ``model`` here is
only what is asked for (``--model``), None for the CLI's default.

Requirements: the ``claude`` command is on PATH and is signed in
(``claude`` then ``/login``). The reviewer is unavailable otherwise, and the
pipeline records it as skipped.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time  # noqa: F401  (tests patch setuhq.reviewers.claude_code.time.sleep to skip the backoff)
from pathlib import Path
from typing import Callable

from setuhq.reviewers.sentinel import RefusalError, Reply, SentinelReviewer
from setuhq.reviewers.task import ReviewError

Runner = Callable[[list[str], str], str]


def _subprocess_runner(cmd: list[str], cwd: str) -> str:
    try:
        completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ReviewError("claude timed out after 600 s") from exc
    if completed.returncode != 0:
        raise ReviewError(f"claude exited with {completed.returncode}: {completed.stderr.strip()[:300]}")
    return completed.stdout


def reported_model(envelope: dict) -> str | None:
    """The model id from the CLI envelope's ``modelUsage``: the one that wrote the most output tokens."""
    usage = envelope.get("modelUsage") if isinstance(envelope, dict) else None
    if not isinstance(usage, dict) or not usage:
        return None

    def out_tokens(item):
        stats = item[1] if isinstance(item[1], dict) else {}
        return stats.get("outputTokens") or 0

    return max(usage.items(), key=out_tokens)[0]


class ClaudeCodeBackend:
    provider = "claude-code"

    def __init__(self, model: str | None = None, *, binary: str = "claude", runner: Runner | None = None):
        self.model = model
        self.binary = binary
        self.runner = runner

    def missing(self) -> str | None:
        if self.runner is not None or shutil.which(self.binary) is not None:
            return None
        return f"the '{self.binary}' command is not on PATH (install Claude Code and sign in)"

    def cache_tag(self) -> str:
        return self.provider

    def request(self, system: str, user: str, image: Path) -> str:
        return (f"{system}\n\n{user}\n\n"
                f"The plot is the PNG at this absolute path: {image}. "
                "Open it with the Read tool, look at it, then reply with only the JSON object.")

    def prompt_parts(self, system: str, user: str, image: Path) -> list[str]:
        return [self.request(system, user, image)]

    def command(self, request: str) -> list[str]:
        cmd = [self.binary, "-p", request, "--output-format", "json", "--allowedTools", "Read"]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def call(self, system: str, user: str, image: Path) -> Reply:
        run = self.runner or _subprocess_runner
        stdout = run(self.command(self.request(system, user, image)), str(image.parent))
        envelope = json.loads(stdout)
        if isinstance(envelope, dict) and envelope.get("is_error"):
            raise ReviewError(f"claude reported an error: {str(envelope.get('result', ''))[:300]}")
        if isinstance(envelope, dict) and envelope.get("stop_reason") == "refusal":
            raise RefusalError("claude-code: the model declined to answer (stop_reason 'refusal')")
        text = envelope.get("result", "") if isinstance(envelope, dict) else str(envelope)
        return Reply(text, reported_model(envelope) if isinstance(envelope, dict) else None)


class ClaudeCodeReviewer(SentinelReviewer):
    """A Sentinel through the Claude Code CLI. Config type ``claude_code``."""

    def __init__(self, reviewer_id: str, persona: str = "volunteer", model: str | None = None, binary: str = "claude",
                 cache_dir: str | Path | None = None, retries: int = 3, runner: Runner | None = None,
                 kind: str = "claude_code"):
        super().__init__(reviewer_id, ClaudeCodeBackend(model, binary=binary, runner=runner),
                         persona=persona, cache_dir=cache_dir, retries=retries, kind=kind)

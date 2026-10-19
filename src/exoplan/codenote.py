"""A run's code note: when a stored run was made with older code whose results a later fix would change, its
manifest carries ``code_note``, and every page built from the run shows it at the top."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

PRE_FIX_NOTE = ("Pre-fix code: made with exoplan up to commit 5a03087, before two fixes that change default results: "
                "preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and vet.py's "
                "odd/even test no longer fails clean deep planets. Not re-run since.")

BANNER_STYLE = ("margin:0;padding:8px 16px;font:14px/1.45 system-ui,-apple-system,'Segoe UI',sans-serif;"
                "background:#4a3800;color:#fff3cc;border-bottom:1px solid #a57c00;position:relative;z-index:50")


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def with_code_note(page: str, note: str | None) -> str:
    """The page with ``note`` as a banner right after the opening ``<body>`` tag (unchanged without a note)."""
    if not note:
        return page
    banner = f'<p class="codenote" role="note" style="{BANNER_STYLE}">{html.escape(note)}</p>'
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + banner, page, count=1)

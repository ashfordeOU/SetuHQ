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

# Fixed to the bottom of the window: it never changes a page's height (the app's panes must fit the window exactly),
# and it lets clicks through except on its dismiss button.
BANNER_STYLE = ("position:fixed;left:0;right:0;bottom:0;z-index:2147483000;margin:0;padding:6px 44px 6px 16px;"
                "font:13px/1.4 system-ui,-apple-system,'Segoe UI',sans-serif;background:rgba(74,56,0,.94);"
                "color:#fff3cc;border-top:1px solid #a57c00;pointer-events:none")
BUTTON_STYLE = ("position:absolute;right:8px;top:50%;transform:translateY(-50%);pointer-events:auto;background:none;"
                "border:1px solid #a57c00;color:#fff3cc;border-radius:4px;font:inherit;line-height:1;padding:2px 7px;"
                "cursor:pointer")


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def with_code_note(page: str, note: str | None) -> str:
    """The page with ``note`` as a banner (fixed to the bottom of the window, dismissable) inserted right after the
    opening ``<body>`` tag; the page is unchanged without a note."""
    if not note:
        return page
    banner = (f'<div class="codenote" role="note" style="{BANNER_STYLE}">{html.escape(note)}'
              f'<button type="button" style="{BUTTON_STYLE}" aria-label="Dismiss this note" '
              f'onclick="this.parentNode.remove()">×</button></div>')
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + banner, page, count=1)

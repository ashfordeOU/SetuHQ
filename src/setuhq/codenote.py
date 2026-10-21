# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A run's code note: when a stored run was made with older code whose results a later fix would change, its
manifest (or the discovery catalogue) carries ``code_note``, a technical account of what changed.

Visitors never see that text. A page whose figures come from such a run shows one plain sentence, as a quiet
note in the page itself (never a site-wide banner), with a "details" link to the Docs page, which quotes the
technical note in full (:func:`technical_note_html`). A run without a note shows nothing.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

PRE_FIX_NOTE = ("Pre-fix code: made with SetuHQ (then called exoplan) up to commit 5a03087, before two fixes that change "
                "default results: preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and vet.py's "
                "odd/even test no longer fails clean deep planets. Not re-run since.")

# The one sentence a visitor reads, wherever a note applies.
VISITOR_TEXT = "These figures come from an earlier version of the pipeline; a re-run on the current code is in progress."
DETAILS_HREF = "/docs/#provenance"
NOTE_CLASS = "provnote"
# Inline so it reads the same on every page (the app's own stylesheet refines .provnote).
NOTE_STYLE = "margin:8px 0;font-size:13px;line-height:1.5"


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def visitor_note(note: str | None, *, details_href: str = DETAILS_HREF) -> str:
    """The quiet one-sentence note for a page built from a run that carries ``note``; empty without one."""
    if not note:
        return ""
    return (f'<p class="{NOTE_CLASS}" role="note" style="{NOTE_STYLE}">{html.escape(VISITOR_TEXT)} '
            f'<a href="{html.escape(details_href)}">Details</a></p>')


def technical_note_html(note: str | None) -> str:
    """The Docs page's account of the note, verbatim (commit, functions and all), or empty."""
    if not note:
        return ""
    return f'<blockquote class="technote"><p>{html.escape(note)}</p></blockquote>'


def with_code_note(page: str, note: str | None, *, details_href: str = DETAILS_HREF) -> str:
    """The page with the quiet note right after its first heading (or, without one, at the start of its body);
    the page is unchanged without a note."""
    if not note:
        return page
    p = visitor_note(note, details_href=details_href)
    if "</h1>" in page:
        return page.replace("</h1>", "</h1>" + p, 1)
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + p, page, count=1)

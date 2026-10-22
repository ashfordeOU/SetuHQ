# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A stored result's code note: when a run or a catalogue was made with older code whose results a later fix would
change, its record (a run's manifest, or the discovery catalogue) carries ``code_note``, a technical account of what
changed.

There is no site-wide banner. A result made on the current code carries no note, and its pages say nothing extra.
Since the re-run on the fixed code (2026-10-21) the stored pi Men run, the live discovery catalogue, the pi Men
validation, the injection-recovery benchmark, the threshold sweep, the real-TOI benchmark and the feed-rule
evaluation are all current. The results kept as the historical pre-fix record carry the pre-fix note in their
own files only (:data:`HISTORICAL`, :func:`historical_note`).

A page built from a record that still carries a note shows one plain sentence, as a quiet note in the page itself
(never a banner, no commit hash, no code name), with a "details" link to the Docs page, which quotes the technical
note in full (:func:`technical_note_html`)."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

PRE_FIX = ("Pre-fix code: made with SetuHQ (then called exoplan) up to commit 5a03087, before two fixes that change "
           "default results: preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and "
           "vet.py's odd/even test no longer fails clean deep planets.")
# The note as a record made before the fixes and not re-run carries it.
PRE_FIX_NOTE = PRE_FIX + " Not re-run since."

# The same caveat for a reader of a page: one plain sentence, no commit hashes or function names.
PLAIN_PRE_FIX = ("These results were made with an earlier version of SetuHQ, before two fixes that change results: very "
                 "deep dips are no longer removed when the light curve is cleaned, and a check that wrongly rejected clean "
                 "deep planets was corrected.")
PLAIN = {PRE_FIX_NOTE: PLAIN_PRE_FIX}

# The pre-fix results kept as the historical record: what each is, and where its re-run on the current code is (None:
# not re-run, with the reason). Each carries historical_note(path) in its own file (a JSON file under "code_note", a
# Markdown file in its opening lines).
HISTORICAL = {
    "docs/discoveries/catalog_v1_fap200.json": ("the live catalogue under the old feed rule", "docs/discoveries/catalog.json"),
    "docs/results/benchmark_real_tois.json": ("the real-TOI benchmark's first run", "docs/results/benchmark_real_tois_clipfix.json"),
    "docs/results/benchmark_real_tois.md": ("the real-TOI benchmark's first run", "docs/results/benchmark_real_tois_clipfix.md"),
    "docs/results/feed_rule_validation.json": ("the feed rule's first held-out evaluation",
                                               "docs/results/feed_rule_validation_clipfix.json"),
    "docs/results/feed_rule_live_rerun.json": ("the live feed's first re-run under the feed rule",
                                               "docs/results/feed_rule_live_rerun_clipfix.json"),
    "docs/results/reviewer_weights_full_panel.calibration.json": (
        "the panel's calibration record", None),
}
NOT_RERUN = {"docs/results/reviewer_weights_full_panel.calibration.json":
             ("Not re-run: its Sentinel rates cannot be measured again without calling the Sentinels, and the weights "
              "are a frozen parameter of the benchmark protocol (see current_code in this file).")}


def historical_note(path: str) -> str:
    """The pre-fix note a historical record carries: where its re-run is, or why it was not re-run."""
    rerun = HISTORICAL[path][1]
    return PRE_FIX + (f" Re-run on the current code: {rerun}." if rerun else " " + NOT_RERUN[path])


# The one sentence a visitor reads, wherever a note applies.
VISITOR_TEXT = "These figures come from an earlier version of the pipeline, made before later fixes that change results."
DETAILS_HREF = "/docs/#provenance"
NOTE_CLASS = "provnote"
# Inline so it reads the same on every page (the app's own stylesheet refines .provnote).
NOTE_STYLE = "margin:8px 0;font-size:13px;line-height:1.5"


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def plain_note(note: str) -> str:
    """The note as a page states it: the plain sentence for a known note; otherwise the note with commit hashes and
    code names (anything in backticks, a dotted or file-like name) left out."""
    if note in PLAIN or note.startswith(PRE_FIX):
        return PLAIN.get(note, PLAIN_PRE_FIX)
    text = re.sub(r"`[^`]*`", "", note)
    text = re.sub(r"\b(?:commit\s+)?[0-9a-f]{7,40}\b", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


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

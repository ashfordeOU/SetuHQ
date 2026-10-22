# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A stored result's code note: when a run or a catalogue was made with older code whose results a later fix would
change, its record carries ``code_note``.

There is no site-wide banner. A result made on the current code carries no note, and its pages say nothing extra.
Since the re-run on the fixed code (2026-10-21) the stored pi Men run, the live discovery catalogue, the pi Men
validation, the injection-recovery benchmark, the threshold sweep, the real-TOI benchmark and the feed-rule
evaluation are all current. The results kept as the historical pre-fix record carry :data:`PRE_FIX_NOTE` in their
own files only (:data:`HISTORICAL`). A page built from a record that still carries a note states it once, in plain
language (:data:`PLAIN`), as an ordinary paragraph at the top of that page: no banner, no commit hash, no code name."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

PRE_FIX_NOTE = ("Pre-fix code: made with SetuHQ (then called exoplan) up to commit 5a03087, before two fixes that change "
                "default results: preprocess.clean no longer deletes dips deeper than 10 times the point-to-point scatter, and vet.py's "
                "odd/even test no longer fails clean deep planets. Not re-run since.")

# The same caveat for a reader of a page: one plain sentence, no commit hashes or function names.
PLAIN = {PRE_FIX_NOTE: ("These results were made with an earlier version of SetuHQ, before two fixes that change results: "
                        "very deep dips are no longer removed when the light curve is cleaned, and a check that wrongly "
                        "rejected clean deep planets was corrected.")}

# The pre-fix results kept as the historical record, each carrying PRE_FIX_NOTE in its own file (a JSON file under
# "code_note", a Markdown file in its opening lines). Their re-runs on the current code sit beside them.
HISTORICAL = {
    "docs/discoveries/catalog_v1_fap200.json": "the live catalogue under the old feed rule (superseded by catalog.json)",
    "docs/results/benchmark_real_tois.json": "the real-TOI benchmark's first run (re-run: benchmark_real_tois_clipfix.json)",
    "docs/results/benchmark_real_tois.md": "the real-TOI benchmark's first run (re-run: benchmark_real_tois_clipfix.md)",
    "docs/results/feed_rule_validation.json": "the feed rule's first held-out evaluation (re-run: feed_rule_validation_clipfix.json)",
    "docs/results/feed_rule_live_rerun.json": "the live feed's first re-run under the feed rule (re-run: feed_rule_live_rerun_clipfix.json)",
    "docs/results/reviewer_weights_full_panel.calibration.json": ("the panel's calibration record; its Sentinel rates cannot be "
                                                                  "measured again without calling the Sentinels"),
}


def code_note(run_dir: str | Path) -> str | None:
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("code_note") or None


def plain_note(note: str) -> str:
    """The note as a page states it: the plain sentence for a known note; otherwise the note with commit hashes and
    code names (anything in backticks, a dotted or file-like name) left out."""
    if note in PLAIN:
        return PLAIN[note]
    text = re.sub(r"`[^`]*`", "", note)
    text = re.sub(r"\b(?:commit\s+)?[0-9a-f]{7,40}\b", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def with_code_note(page: str, note: str | None) -> str:
    """The page with ``note`` stated once, in plain language, as an ordinary paragraph right after ``<body>``; the
    page is unchanged without a note. No banner: nothing fixed, dismissable or scripted."""
    if not note:
        return page
    para = (f'<p class="codenote" role="note" style="margin:0;padding:8px 16px;font:13px/1.4 system-ui,sans-serif">'
            f'{html.escape(plain_note(note))}</p>')
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + para, page, count=1)

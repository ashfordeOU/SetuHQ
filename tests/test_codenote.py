# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A run's code note: one quiet sentence on the pages built from it, never a banner."""

import json

from setuhq.codenote import PRE_FIX_NOTE, VISITOR_TEXT, code_note, with_code_note


def test_no_banner_one_quiet_sentence_after_the_heading(tmp_path):
    page = '<html><head></head><body class="x"><main><h1>Plates</h1><p>hi</p></main></body></html>'
    out = with_code_note(page, "Pre-fix code: <old> 5a03087")
    assert out.index("</h1>") < out.index('class="provnote"') < out.index("<p>hi")
    # Plain words for visitors; the technical text (commit, functions) is behind the Details link, on the Docs page.
    assert VISITOR_TEXT in out and "5a03087" not in out and "&lt;old&gt;" not in out and 'href="/docs/#provenance"' in out
    assert "codenote" not in out and "position:fixed" not in out and "background" not in out
    assert with_code_note(page, None) == page
    # Without a heading, it opens the body.
    assert with_code_note("<body><p>x</p></body>", "n").startswith('<body>\n<p class="provnote"')
    assert VISITOR_TEXT.count(".") == 1  # one sentence


def test_the_stored_run_carries_the_pre_fix_note(tmp_path):
    assert code_note("runs/tess-pi-men-s1") == PRE_FIX_NOTE
    (tmp_path / "manifest.json").write_text(json.dumps({"config_name": "x"}))
    assert code_note(tmp_path) is None
    assert json.loads(open("docs/discoveries/catalog.json").read())["code_note"] == PRE_FIX_NOTE
    assert "confirmed" not in PRE_FIX_NOTE.lower()

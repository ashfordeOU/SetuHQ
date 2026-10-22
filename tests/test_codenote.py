# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A run's code note: one quiet sentence on the pages built from it, never a banner."""

import json

from setuhq.codenote import PRE_FIX_NOTE, VISITOR_TEXT, code_note, with_code_note


def test_a_note_is_plain_language_on_its_page_never_a_banner(tmp_path):
    from setuhq.codenote import PLAIN, plain_note

    assert plain_note(PRE_FIX_NOTE) == PLAIN[PRE_FIX_NOTE]
    assert "5a03087" not in PLAIN[PRE_FIX_NOTE] and "preprocess" not in PLAIN[PRE_FIX_NOTE] and "vet.py" not in PLAIN[PRE_FIX_NOTE]
    page = '<html><head></head><body class="x"><main>hi</main></body></html>'
    out = with_code_note(page, PRE_FIX_NOTE)
    assert out.index('class="provnote"') > out.index('<body class="x">') and out.index('class="provnote"') < out.index("<main>")
    assert "5a03087" not in out and "preprocess" not in out and "vet.py" not in out
    # no banner: nothing fixed, dismissable or scripted
    assert "<script" not in out and "position:fixed" not in out and "button" not in out and "localStorage" not in out
    assert with_code_note(page, None) == page


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


def test_current_results_carry_no_note_and_the_historical_ones_keep_theirs(tmp_path):
    from pathlib import Path

    from setuhq.codenote import HISTORICAL, historical_note

    # Re-run on the current code: no note, so no banner on any page built from them.
    assert code_note("runs/tess-pi-men-s1") is None
    (tmp_path / "manifest.json").write_text(json.dumps({"config_name": "x"}))
    assert code_note(tmp_path) is None
    assert "code_note" not in json.loads(open("docs/discoveries/catalog.json").read())
    for f in ("docs/results/pi_men_validation.md", "docs/results/injection_recovery_simulated_panel.md", "docs/threshold_sweep.md",
              "docs/results/benchmark_real_tois_clipfix.md", "docs/leaderboard/leaderboard.md", "docs/paper/paper.md"):
        assert PRE_FIX_NOTE not in Path(f).read_text(), f
    for page in Path("site").rglob("*.html"):
        assert 'class="codenote"' not in page.read_text() and 'class="provnote"' not in page.read_text(), page
    # Kept as the historical pre-fix record: each says so in its own file.
    for f in HISTORICAL:
        text = Path(f).read_text()
        note = historical_note(f)
        assert "Not re-run since" not in note  # each names its re-run, or why there is none
        if f.endswith(".json"):
            assert json.loads(text)["code_note"] == note, f
        else:
            assert note in text[:2000], f
        rerun = HISTORICAL[f][1]
        assert rerun is None or (Path(rerun).exists() and f"Re-run on the current code: {rerun}." in note), f
    assert "confirmed" not in PRE_FIX_NOTE.lower()

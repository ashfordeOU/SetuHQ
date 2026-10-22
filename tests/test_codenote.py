# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A run's code note reaches the top of every page built from it."""

import json

from setuhq.codenote import PRE_FIX_NOTE, code_note, with_code_note


def test_a_note_is_one_plain_sentence_on_its_page_never_a_banner(tmp_path):
    from setuhq.codenote import PLAIN

    page = '<html><head></head><body class="x"><main>hi</main></body></html>'
    out = with_code_note(page, PRE_FIX_NOTE)
    assert out.index('class="codenote"') > out.index('<body class="x">') and out.index('class="codenote"') < out.index("<main>")
    assert PLAIN[PRE_FIX_NOTE] in out and "5a03087" not in out and "preprocess" not in out and "vet.py" not in out
    # no banner: nothing fixed, dismissable or scripted
    assert "<script" not in out and "position:fixed" not in out and "button" not in out and "localStorage" not in out
    assert with_code_note(page, None) == page
    assert "&lt;old&gt;" in with_code_note(page, "Older code: <old>")  # escaped


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
        assert 'class="codenote"' not in page.read_text(), page
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

"""A run's code note reaches the top of every page built from it."""

import json

from setuhq.codenote import PRE_FIX_NOTE, code_note, with_code_note


def test_banner_goes_right_after_body(tmp_path):
    page = '<html><head></head><body class="x"><main>hi</main></body></html>'
    out = with_code_note(page, "Pre-fix code: <old>")
    assert out.index('class="codenote"') > out.index('<body class="x">')
    assert out.index('class="codenote"') < out.index("<main>")
    assert "Pre-fix code: &lt;old&gt;" in out                # escaped
    assert with_code_note(page, None) == page
    # a 44 x 44 px dismiss button; the banner takes taps (no pointer-events:none); the dismissal is remembered
    assert "width:44px;height:44px" in out and "pointer-events:none" not in out
    assert "localStorage.setItem" in out and "catch(e)" in out and "data-fixed=" in out and "position:relative" in out
    # in the fixed bar the note is one line with a "more" button that opens it
    assert "text-overflow:ellipsis" in out and 'class="cn-more"' in out and "aria-expanded" in out


def test_the_stored_run_carries_the_pre_fix_note(tmp_path):
    assert code_note("runs/tess-pi-men-s1") == PRE_FIX_NOTE
    (tmp_path / "manifest.json").write_text(json.dumps({"config_name": "x"}))
    assert code_note(tmp_path) is None
    assert json.loads(open("docs/discoveries/catalog.json").read())["code_note"] == PRE_FIX_NOTE
    assert "confirmed" not in PRE_FIX_NOTE.lower()

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""setuhq.design: one token source for both themes, readable contrast, one motion curve and three durations
everywhere, and the font fallbacks that match Geist's metrics."""

import importlib.util
import re
from pathlib import Path

import pytest

from setuhq import design as D

ROOT = Path(__file__).resolve().parents[1]


def _rgb(c: str, under=(255, 255, 255)) -> tuple[float, float, float]:
    if c.startswith("#"):
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b, a = (float(x) for x in c[c.index("(") + 1:-1].split(","))
    return tuple(v * a + u * (1 - a) for v, u in zip((r, g, b), under))


def _lum(c) -> float:
    ch = [v / 255 for v in c]
    ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(fg: str, bg: str) -> float:
    b = _rgb(bg)
    a, c = _lum(_rgb(fg, b)), _lum(b)
    return (max(a, c) + 0.05) / (min(a, c) + 0.05)


def test_both_themes_have_the_same_tokens():
    css = D.tokens_css()
    dark, light, system = re.findall(r"\{([^{}]*)\}", css)
    names = lambda block: sorted(re.findall(r"--([\w-]+):", block))  # noqa: E731
    assert set(names(light)) == set(D.TOKENS) == set(names(system)) and set(D.TOKENS) <= set(names(dark))
    assert all(len(v) == 2 for v in D.TOKENS.values())
    assert D.TOKENS["bg"] == ("#04060B", "#F5F5F7") and D.TOKENS["blue"][0] == "#0A84FF"  # the logo's blue stays
    assert D.TOKENS["stage"] == ("#000000", "#000000")  # planet art keeps a black stage in light mode


@pytest.mark.parametrize("theme", [0, 1])
def test_ink_and_accents_are_readable(theme):
    t = {k: v[theme] for k, v in D.TOKENS.items()}
    for fg in ("ink", "ink-2", "ink-3"):
        for bg in ("bg", "bg-2", "panel", "bg-3"):
            assert contrast(t[fg], t[bg]) >= 4.5, (theme, fg, bg)
    for fg in ("blue", "sen", "prb", "yellow", "red", "green"):
        assert contrast(t[fg], t["bg"]) >= 3, (theme, fg)
    for fg in ("stage-ink", "stage-dim"):
        assert contrast(t[fg], "#000000") >= 4.5


def test_the_token_sheet_parses_and_scopes():
    for css in (D.tokens_css(), D.tokens_css(".shellscope"), D.tokens_css(":root", aliases=D.DOCKET_ALIASES), D.PRINT_CSS):
        assert css.count("{") == css.count("}")
        for decl in re.findall(r"\{([^{}]*)\}", css):
            assert all(re.fullmatch(r"\s*(--[\w-]+|color-scheme)\s*:[^;]+", d) for d in decl.split(";") if d.strip()), decl[:80]
    scoped = D.tokens_css(".shellscope")
    assert scoped.startswith(".shellscope{") and ':root[data-theme="light"] .shellscope{' in scoped
    assert '@media (prefers-color-scheme: light){:root[data-theme="system"] .shellscope{' in scoped
    assert "--paper:var(--bg)" in D.tokens_css(":root", aliases=D.DOCKET_ALIASES)
    from setuhq.site import shell_css
    assert ':root[data-theme="light"] .shellscope{' in shell_css()


def test_aliases_point_at_real_tokens():
    for aliases in (D.DOCKET_ALIASES, D.PLATE_ALIASES, D.REPORT_ALIASES):
        assert set(aliases.values()) <= set(D.TOKENS)
    assert set(D.STATUS) == {"passed", "flagged", "rejected", "known"}
    from setuhq.galaxy import METHOD_COLOUR
    assert {k: v[0] for k, v in D.METHOD.items()} == METHOD_COLOUR  # on a stage, always the dark value


def _all_css() -> dict[str, str]:
    from setuhq import app, brand, dashboard, docket, plate, renderer, report, site
    return {"app.APP_CSS": app.APP_CSS, "site.SITE_CSS": site.SITE_CSS, "site.STARFIELD": site.STARFIELD,
            "renderer.RENDER_CSS": renderer.RENDER_CSS, "docket.DOCKET_CSS": docket.DOCKET_CSS, "plate.PLATE_CSS": plate.PLATE_CSS,
            "report.STYLE": report.STYLE, "dashboard.DASHBOARD_CSS": dashboard.DASHBOARD_CSS, "brand.LOGO_CSS": brand.LOGO_CSS,
            "design": D.BASE_CSS + D.MOTION_CSS, "fonts.css": (ROOT / "src/setuhq/fonts/fonts.css").read_text()}


def test_one_motion_curve_and_three_durations_everywhere():
    problems = [p for k, css in _all_css().items() for p in D.motion_problems(css, k)]
    assert problems == []
    assert D.CONST["ease"] == "cubic-bezier(.2,.7,.2,1)" and [D.CONST[f"d-{i}"] for i in (1, 2, 3)] == ["150ms", "350ms", "600ms"]
    # Under reduced motion every duration is 0 ms.
    assert re.search(r"prefers-reduced-motion:reduce\)\{\s*:root\{--d-1:0ms;--d-2:0ms;--d-3:0ms\}", D.MOTION_CSS)
    # The lint itself catches what it should.
    assert D.motion_problems(".a{transition:color .2s ease-in-out}", "t") and D.motion_problems(".a{transition:x 150ms cubic-bezier(.2,.8,.2,1)}", "t")
    assert not D.motion_problems(".a{animation:twinkle 6s var(--ease) infinite}.b{transition:color var(--d-1) var(--ease)}", "t")


def test_font_fallbacks_match_a_recomputation():
    spec = importlib.util.spec_from_file_location("font_fallback", ROOT / "tools" / "font_fallback.py")
    ff = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ff)
    assert ff.fallback_values() == D.FONT_FALLBACK
    css = (ROOT / "src/setuhq/fonts/fonts.css").read_text()
    assert D.fallback_faces_css() in css
    assert '"Geist Fallback"' in D.SANS and '"Geist Mono Fallback"' in D.MONO
    assert (ROOT / "src/setuhq/fonts" / D.FONT_PRELOAD.replace("/assets/fonts/", "")).is_file()


def test_a_rate_is_never_shown_without_its_interval():
    with pytest.raises(ValueError):
        D.odometer_html("60%", is_rate=True)
    out = D.odometer_html("60%", is_rate=True, rate=(90, 150, 0.52, 0.67))
    assert "90 of 150 (52–67%)" in out and 'data-odo="60%"' in out and ">60%<" in out

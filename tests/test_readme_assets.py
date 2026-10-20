# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The README's generated figures, brand files and app screenshots: present in both themes, self-contained,
described exactly (the README's alt text is each figure's own <desc>), recorded (SHOTS.json covers every
screenshot) and current (tools/gen_readme_assets.py --check, the slow test)."""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "tools" / "gen_readme_assets.py"
README = ROOT / "README.md"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("gen_readme_assets", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def manifest():
    return json.loads((ROOT / "docs" / "assets" / "readme" / "MANIFEST.json").read_text(encoding="utf-8"))


def _svgs():
    return sorted((ROOT / "docs" / "assets" / "readme").glob("*.svg")) + sorted((ROOT / "docs" / "assets" / "brand").glob("*.svg"))


def test_every_figure_has_both_variants_and_a_desc_naming_its_source_and_commit(gen, manifest):
    assert set(manifest["assets"]) == set(gen.FIGURES)
    for name, entry in manifest["assets"].items():
        assert entry["files"] == [f"{name}-light.svg", f"{name}-dark.svg"]
        descs = []
        for fn in entry["files"]:
            svg = (ROOT / "docs" / "assets" / "readme" / fn).read_text(encoding="utf-8")
            desc = gen.svg_desc(svg)
            assert len(desc) > 200, fn
            assert f"commit {entry['commit']}" in desc, fn
            assert any(src in desc for src in entry["sources"]), fn
            descs.append(desc)
        assert descs[0] == descs[1], f"{name}: the light and dark variants must say the same thing"


def test_every_svg_is_self_contained_and_fully_outlined():
    files = _svgs()
    assert len(files) == 24  # 8 figures x 2 themes, and 8 brand files
    for p in files:
        svg = p.read_text(encoding="utf-8")
        assert svg.startswith("<svg "), p.name
        assert "<text" not in svg and "@font-face" not in svg and "font-family" not in svg, f"{p.name}: live text"
        assert "<script" not in svg and "<image" not in svg, p.name
        for href in re.findall(r'href="([^"]*)"', svg):
            assert href.startswith("#"), f"{p.name}: external reference {href}"
        assert re.search(r'<desc id="d">[^<]+</desc>', svg), p.name


def test_brand_files_are_the_approved_logo(gen):
    brand = ROOT / "docs" / "assets" / "brand"
    names = {p.name for p in brand.glob("*.svg")}
    assert names == {"setuhq-logo-light.svg", "setuhq-logo-dark.svg", "setuhq-wordmark-light.svg", "setuhq-wordmark-dark.svg",
                     "setuhq-icon-black.svg", "setuhq-icon-navy.svg", "setuhq-favicon.svg", "setuhq-social-card.svg"}
    light = (brand / "setuhq-logo-light.svg").read_text(encoding="utf-8")
    dark = (brand / "setuhq-logo-dark.svg").read_text(encoding="utf-8")
    assert "#0A1226" in light and "#0071E3" in light and "#64D2FF" in light
    assert "#F5F5F7" in dark and "#0A84FF" in dark and "#64D2FF" in dark
    # The Q is geometry: a ring, a planet dot about 0.3 times its radius, and a round-capped tail.
    q = gen.q_geometry()
    assert q["planet"][2] == pytest.approx(0.3 * q["r"])
    assert 2 * (q["r"] + q["stroke"] / 2) == pytest.approx(q["top"] - q["bottom"])  # the O's height, overshoot included
    assert 'stroke-linecap="round"' in light
    fav = (brand / "setuhq-favicon.svg").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in fav
    card = (brand / "setuhq-social-card.svg").read_text(encoding="utf-8")
    assert 'width="1200" height="630"' in card


def test_readme_alt_text_is_each_figures_desc_and_every_picture_is_paired(gen):
    assert gen.check_readme() == []
    pics = gen.readme_pictures(README.read_text(encoding="utf-8"))
    assert len(pics) == 18  # the logo, 8 figures and 9 screenshots
    for p in pics:
        assert p["light"].endswith(("-light.svg", "-light.webp")) and p["dark"] == p["light"].replace("-light.", "-dark.")


def test_shots_json_covers_every_screenshot_with_one_frame_rule(gen):
    assert gen.check_shots() == []
    rec = json.loads((ROOT / "docs" / "assets" / "readme" / "app" / "SHOTS.json").read_text(encoding="utf-8"))
    views = {s["view"] for s in rec["shots"]}
    assert {"overview", "galaxy", "catalogue", "planet", "transit", "mission"} <= views
    assert len([v for v in views if v.startswith("methods-")]) >= 2
    for s in rec["shots"]:
        assert s["viewport"] == {"width": 1440, "height": 900} and s["device_scale_factor"] == 2 and s["reduced_motion"]
        assert (s["crop_css_px"]["width"], s["crop_css_px"]["height"]) == (1360, 850)
        assert (s["width"], s["height"]) == (1600, 1000)


def test_readme_images_weigh_under_six_megabytes(gen):
    text = README.read_text(encoding="utf-8")
    srcs = set(re.findall(r'(?:src|srcset)="(docs/assets/[^"]+)"', text))
    total = sum((ROOT / s).stat().st_size for s in srcs)
    assert total < 6_000_000, total


def test_readme_never_overclaims():
    text = README.read_text(encoding="utf-8")
    assert "SuperIntelligence" not in text
    assert ("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. "
            "Probes are deterministic matched-filter detectors.") in text.replace("Probes are\n", "Probes are ")
    for bad in ("SetuHQ discovered", "SetuHQ confirmed", "we discovered", "newly discovered planet", "Continuous discovery",
                "Discovery candidates", "published vetters"):
        assert bad.lower() not in text.lower(), bad


# ---------- every text run fits its card: no figure is cut ----------
def _fit_problems(svg, name: str, margin: float = 8) -> list[str]:
    """A text run must lie inside the smallest card that holds its start (4 px clear of each side), or, outside every
    card, inside the figure (8 px clear; a logo, cropped to its box, 0). Widths are the outlined glyphs' advances, as drawn."""
    bad = []
    for x0, x1, y, size, txt in svg.runs:
        # every card the run touches (any part of it, not just its start)
        cards = [(px, py, pw, ph) for px, py, pw, ph in svg.panels if x0 < px + pw and x1 > px and py <= y <= py + ph]
        if cards:
            px, py, pw, ph = min(cards, key=lambda c: c[2] * c[3])
            if x0 < px + 4 - 1e-6 or x1 > px + pw - 4 + 1e-6:
                bad.append(f"{name}: {txt!r} spans x {x0:.0f}–{x1:.0f}, its card x {px:.0f}–{px + pw:.0f}")
        elif x0 < margin or x1 > svg.w - margin or y > svg.h:
            bad.append(f"{name}: {txt!r} spans x {x0:.0f}–{x1:.0f}, outside the {svg.w:.0f} px figure")
    # a run that touches a plot ellipse (the sky map) lies wholly inside it
    for cx, cy, rx, ry in svg.ellipses:
        for x0, x1, y, size, txt in svg.runs:
            top = y - 0.75 * size
            if x1 < cx - rx or x0 > cx + rx or y < cy - ry or top > cy + ry:
                continue
            if any(((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 > 1 for px in (x0, x1) for py in (top, y)):
                bad.append(f"{name}: {txt!r} crosses the plot's rim")
    # and no two runs collide: overlapping in x on (nearly) the same line
    runs = sorted(svg.runs, key=lambda r: (r[2], r[0]))
    for i, (a0, a1, ay, asz, at) in enumerate(runs):
        for b0, b1, by, bsz, bt in runs[i + 1:]:
            if by - ay >= 0.8 * min(asz, bsz):
                break
            if min(a1, b1) - max(a0, b0) > 1:
                bad.append(f"{name}: {at!r} and {bt!r} overlap at y {ay:.0f}")
    return bad


def test_every_text_run_fits_its_card_in_every_figure(gen):
    bad, checked = [], 0
    cache = {}
    for name, (fn, loader, _) in gen.FIGURES.items():
        data = cache.setdefault(loader, loader())
        for t in gen.THEMES:
            svg = fn(t, data)
            assert svg.runs, name
            checked += len(svg.runs)
            bad += _fit_problems(svg, f"{name}-{t['name']}")
    for th in ("light", "dark"):
        for name, svg in ((f"logo-{th}", gen.brand_lockup(th)), (f"wordmark-{th}", gen.brand_wordmark(th))):
            bad += _fit_problems(svg, name, margin=0)   # a logo is cropped to its own box
    bad += _fit_problems(gen.brand_social(), "social-card")
    assert checked > 500
    assert bad == [], "\n".join(bad)


def test_fit_check_catches_an_overflowing_run(gen):
    svg = gen.Svg(400, 200, "t", "d")
    gen.panel(svg, gen.DARK, 20, 20, 120, 100)
    svg.text("a phrase far too long for this card", 30, 60, 14, "#fff")
    assert len(_fit_problems(svg, "probe")) == 1
    svg2 = gen.Svg(400, 200, "t", "d")
    svg2.text("left run", 20, 60, 14, "#fff")
    svg2.text("collides", 60, 61, 14, "#fff")
    assert any("overlap" in p for p in _fit_problems(svg2, "probe"))
    svg3 = gen.Svg(400, 200, "t", "d")
    svg3.ellipses.append((200, 100, 150, 75))
    svg3.text("12h", 50, 96, 10, "#fff", anchor="middle")   # centred on the rim: half outside
    assert any("rim" in p for p in _fit_problems(svg3, "probe"))
    words = gen.wrap("vetting only, on detected TCEs, P < 100 d", 160, 10, "mono")
    assert any("P < 100 d" in ln for ln in words), words


# ---------- the README's generated parts ----------
def test_readme_generated_blocks_and_badges_come_from_the_data(gen):
    text = README.read_text(encoding="utf-8")
    for name in gen.README_BLOCKS:
        assert f"<!-- generated:{name} " in text and f"<!-- /generated:{name} -->" in text, name
    blocks = gen.readme_blocks()
    rc = gen.repo_counts()
    b = json.loads((ROOT / "docs/results/benchmark_real_tois.json").read_text(encoding="utf-8"))
    c = b["summary"]["held_out"]["completeness"]
    badges = blocks["badges"]
    assert f"tests-{rc['tests']}%20collected" in badges
    assert f"{rc['tests'] - rc['network'] - rc['slow']} run offline in CI" in badges
    assert f"{round(100 * c['rate'])}%25%20%28{c['k']}%2F{c['n']}%29" in badges
    assert "catalogue-8%2C376%20planets" in badges and f"Methods-{len(gen.MX.CHAPTERS)}%20chapters" in badges
    assert gen.render_readme(text) == text, "run python3 tools/gen_readme_assets.py --write-readme"


def test_pi_men_results_match_the_stored_run(gen):
    import csv

    block = gen.pimen_results_block() + "\n" + gen.sentinel_results_block()
    cands = json.loads((ROOT / "runs/tess-pi-men-s1/candidates.json").read_text(encoding="utf-8"))
    passed = sum(c["passed"] for c in cands)
    assert f"{len(cands)} consensus dips: {passed} passed vetting" in block
    assert len(cands) - passed >= 1 and f"and {len(cands) - passed} failed it" in block
    # Every Sentinel row as stored: its label and confidence appear, and no stale "instrumental" claim does.
    with open(ROOT / "runs/tess-pi-men-s1/classifications.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["user_name"].startswith("claude"):
                conf = json.loads(row["metadata"])["confidence"]
                assert f"`{row['label']}` (confidence {conf:g})" in block
    assert "instrumental" not in block


def test_benchmark_compares_matched_bins_and_words_the_verdict_from_the_intervals(gen):
    d = gen.bench_data()
    by = {c["key"]: c for c in d["cmp"]}
    assert (by["pht_mid"]["ours"]["k"], by["pht_mid"]["ours"]["n"]) == (4, 9)
    assert (by["pht_hi"]["ours"]["k"], by["pht_hi"]["ours"]["n"]) == (77, 102)
    for c in d["cmp"]:
        o = c["ours"]
        want = "below" if o["hi"] < c["ref"] else "above" if o["lo"] > c["ref"] else "consistent"
        assert c["verdict"] == want
    assert by["pht_mid"]["verdict"] == "consistent" and by["pht_hi"]["verdict"] == "below"
    assert "vetting only, on detected TCEs" in by["robovetter"]["note"]
    sentence = gen.bench_verdict(d)
    assert "consistent with Planet Hunters TESS's rate at 3 to 4 R⊕" in sentence
    assert "vetter" not in gen.bench_desc(d).replace("Robovetter", "")


def _shallow() -> bool:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"], capture_output=True, text=True)
    except OSError:
        return True
    return out.returncode != 0 or out.stdout.strip() == "true"


def test_hosted_ci_has_the_history_the_check_needs():
    """CI sets CI_REQUIRE_README_CHECK: there a shallow clone is a failure, not a skip."""
    if os.environ.get("CI_REQUIRE_README_CHECK") and _shallow():
        pytest.fail("shallow clone in CI: set fetch-depth: 0 so tools/gen_readme_assets.py --check can name each source's commit")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in ci and "tools/gen_readme_assets.py --check" in ci and "CI_REQUIRE_README_CHECK" in ci


@pytest.mark.slow
def test_generator_check_passes():
    if _shallow():
        if os.environ.get("CI_REQUIRE_README_CHECK"):
            pytest.fail("shallow clone: the README check needs the full git history")
        pytest.skip("each figure names its source's commit, which needs the full git history")
    out = subprocess.run([sys.executable, str(GEN), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr

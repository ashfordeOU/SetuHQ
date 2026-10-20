"""The README's generated figures, brand files and app screenshots: present in both themes, self-contained,
described exactly (the README's alt text is each figure's own <desc>), recorded (SHOTS.json covers every
screenshot) and current (tools/gen_readme_assets.py --check, the slow test)."""
import importlib.util
import json
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
    assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in text
    for bad in ("SetuHQ discovered", "SetuHQ confirmed", "we discovered", "newly discovered planet"):
        assert bad.lower() not in text.lower()


def _shallow() -> bool:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"], capture_output=True, text=True)
    except OSError:
        return True
    return out.returncode != 0 or out.stdout.strip() == "true"


@pytest.mark.slow
@pytest.mark.skipif(_shallow(), reason="each figure names its source's commit, which needs the full git history")
def test_generator_check_passes():
    out = subprocess.run([sys.executable, str(GEN), "--check"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr

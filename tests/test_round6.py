import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from exoplan import docket as docket_mod
from exoplan.app import APP_CSS, APP_JS, FRAME_BRIDGE_JS, THEME_BUTTON, LANDING_JS, build_app, build_landing
from exoplan.plate import build_plate
from exoplan.report import build_report

from test_story import run_dir, targets  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


def _lum(hexc: str) -> float:
    hexc = hexc.lstrip("#")
    if len(hexc) == 3:
        hexc = "".join(c * 2 for c in hexc)
    out = []
    for i in (0, 2, 4):
        c = int(hexc[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9A-Fa-f]{3,6})\b", block))


def _dark():
    return _tokens(re.search(r":root\{color-scheme:dark;(.*?)\}", APP_CSS, re.S).group(1))


def _light():
    return _tokens(re.search(r':root\[data-theme="light"\]\{color-scheme:light;(.*?)\}', APP_CSS, re.S).group(1))


def test_filled_buttons_meet_4_5_to_1_in_both_themes():
    for t in (_dark(), _light()):
        assert t["btn-bg"].upper() == "#0071E3" and t["btn-ink"].upper() == "#FFFFFF"
        assert ratio(t["btn-ink"], t["btn-bg"]) >= 4.5
    assert round(ratio("#FFFFFF", "#0071E3"), 2) >= 4.69 and ratio("#FFFFFF", "#0A84FF") < 4.5
    # #0A84FF stays for dots, strokes and the "known" status colour.
    assert _dark()["blue"].upper() == "#0A84FF"
    for sel in (".skip{", ".btn.primary{", ".seg .btn[aria-pressed=\"true\"]{", ".cmpbtn[aria-pressed=\"true\"]{"):
        rule = APP_CSS[APP_CSS.index(sel):APP_CSS.index("}", APP_CSS.index(sel))]
        assert "var(--btn-bg)" in rule, sel


def test_light_theme_text_pairs_meet_4_5_to_1():
    t = _light()
    assert t["ink-3"].upper() == "#5E5E63" and t["yellow"].upper() == "#7A5600"
    for fg in ("ink", "ink-2", "ink-3", "blue", "yellow", "red", "green", "sen", "prb", "prb-ink", "star", "cyan", "amber", "coral"):
        for bg in ("bg", "bg-2", "panel"):
            assert ratio(t[fg], t[bg]) >= 4.5, (fg, bg, round(ratio(t[fg], t[bg]), 2))
    # The light block used with the system preference is the same.
    sysblock = _tokens(re.search(r'@media \(prefers-color-scheme: light\)\{:root\[data-theme="system"\]\{color-scheme:light;(.*?)\}\}', APP_CSS, re.S).group(1))
    assert sysblock == t


def test_dark_theme_text_pairs_meet_4_5_to_1():
    t = _dark()
    for fg in ("ink", "ink-2", "ink-3", "blue", "yellow", "red", "green", "sen", "prb-ink", "star", "cyan", "amber", "coral"):
        for bg in ("bg", "bg-2", "panel"):
            assert ratio(t[fg], t[bg]) >= 4.5, (fg, bg, round(ratio(t[fg], t[bg]), 2))


def test_sky_names_simbad_in_its_note_and_its_pin(tmp_path):
    out = build_app(Path("runs/tess-pi-men-s1"), tmp_path / "app", title="t", catalog_path="docs/discoveries/catalog.json")
    page = out.read_text()
    assert ("Field stars decorative · feed stars not plotted (positions not stored) · pi Men placed from SIMBAD "
            "(ICRS J2000) · dashed: the ecliptic") in page
    pin = re.search(r'<a class="skypin"[^>]*>', page).group(0)
    assert 'title="pi Men placed from SIMBAD (ICRS J2000): RA 84.29°, Dec -80.47°"' in pin


def _node(script: str):
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_sky_filters_round_trip_through_the_url():
    fns = re.search(r"const SKY_STATUS = .*?\nconst encodeSkyView = .*?\n", APP_JS, re.S).group(0)
    script = fns + """
const cases = ['status=known,open,rejected&who=all', 'status=open&who=probes', 'status=none&who=split', '', 'status=zzz&who=nobody', 'status=rejected,known'];
console.log(JSON.stringify(cases.map(c => { const v = decodeSkyView(new URLSearchParams(c)); return [v, encodeSkyView(v)]; })));"""
    out = _node(script)
    assert out[0][1] == "status=known,open,rejected&who=all"
    assert out[1][0] == {"status": ["open"], "who": "probes"} and out[1][1] == "status=open&who=probes"
    assert out[2][0]["status"] == [] and out[2][1] == "status=none&who=split"
    assert out[3][1] == out[4][1] == "status=known,open,rejected&who=all"  # missing or bad: the default
    assert out[5][1] == "status=known,rejected&who=all"  # order normalised
    handler = re.search(r"\$\('#route-sky'\)\.addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    assert handler.count("syncSkyURL(true)") == 2
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "applySky(decodeSkyView(p.params))" in go and "syncSkyURL(false)" in go


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_explorer_filters_round_trip_through_the_url():
    fns = re.search(r"const EX_SNR = .*?\nfunction encodeExView\(v\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = "const TICS = [348835438, 349088467, 348770361];\n" + fns + """
const cases = ['stars=all&snr=0&new=1&known=1', 'stars=349088467&snr=8&new=0&known=1', 'stars=none&snr=10&new=1&known=0', '', 'stars=1,2&snr=5&new=x', 'stars=348770361,348835438'];
console.log(JSON.stringify(cases.map(c => { const v = decodeExView(new URLSearchParams(c)); return [v, encodeExView(v)]; })));"""
    out = _node(script)
    # Defaults are left out of the URL, but the long form still parses (older links keep working).
    assert out[0][1] == ""
    assert out[1][1] == "stars=349088467&snr=8&new=0" and out[1][0]["new"] is False
    assert out[2][1] == "stars=none&snr=10&known=0"
    assert out[3][1] == out[4][1] == ""  # missing or bad: the default
    assert out[5][1] == "stars=348835438,348770361"
    sync = re.search(r"function syncFeedURL\(push\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "encodeExView(currentEx())" in sync
    handler = re.search(r"\$\('#route-explorer'\)\.addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    assert handler.count("syncFeedURL(true)") == 3
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "applyEx(decodeExView(p.params))" in go


def test_collapsed_signal_buttons_name_their_dip_list():
    js = docket_mod.DOCKET_JS
    assert "list.id = 'dips-' + s.signal_id.replace(" in js and "list.appendChild(d)" in js
    acc = re.search(r"function accordion\(\)\{.*?\n  \}\n", docket_mod.DOCKET_JS, re.S).group(0)
    assert "h.setAttribute('aria-controls', lst.id)" in acc and "removeAttribute('aria-controls')" in acc


def test_no_built_page_loads_google_fonts(run_dir, tmp_path):  # noqa: F811
    pages = [build_app(run_dir, tmp_path / "app", title="t"), build_landing(run_dir, tmp_path / "index.html", title="t"),
             docket_mod.build_docket(run_dir, tmp_path / "docket", title="t"), build_plate(run_dir, tmp_path / "plate", title="t"),
             build_report(run_dir, tmp_path / "report", title="t")]
    for p in pages:
        text = Path(p).read_text()
        assert "googleapis" not in text and "gstatic" not in text, p
        assert not re.search(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", text), p


def test_archived_report_has_icon_44px_nav_and_wrapped_tables(run_dir, tmp_path):  # noqa: F811
    page = Path(build_report(run_dir, tmp_path / "report", title="t")).read_text()
    assert "<link rel='icon' href='data:,'>" in page
    assert re.search(r"nav a\{[^}]*min-height:44px", page)
    for m in re.finditer(r"<table", page):
        assert "class='scroll'" in page[max(0, m.start() - 120):m.start()], page[m.start() - 120:m.start()]
    landing = Path(build_landing(run_dir, tmp_path / "index.html", title="t")).read_text()
    assert '<a href="report/">Full run report (archived)</a>' in landing


def test_theme_control_says_dark_is_the_default():
    assert '<span class="themelbl">Dark (default)</span>' in THEME_BUTTON and "dark (default)" in THEME_BUTTON
    assert "dark: 'Dark (default)'" in APP_JS and "dark: 'Dark (default)'" in LANDING_JS

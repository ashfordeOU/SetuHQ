# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Localisation (docs/TRANSLATING.md): the catalogues, the message format, the checks every translation passes,
the built site in every language and the tool's language choice."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from setuhq import i18n
from setuhq import i18n_tools as it

ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION_EN = ("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. "
                  "Probes are deterministic matched-filter detectors.")


# ---------- the catalogues ----------
def test_the_english_catalogue_is_what_the_code_declares():
    have = json.loads((ROOT / "src/setuhq/locales/en.arb").read_text(encoding="utf-8"))
    assert it.dumps(it.code_part(have)) == it.dumps(it.code_part(it.extract(pages=False)))  # page text follows site/
    for lang in i18n.TRANSLATIONS:
        assert i18n.catalogue_path(lang).read_text(encoding="utf-8") == it.dumps(it.sync(lang)), lang


def test_every_translation_passes_every_check():
    assert it.check() == []


def test_sixteen_languages_fully_translated_and_marked_machine():
    assert i18n.TRANSLATIONS == ("nl", "pl", "pt", "fi", "sv", "da", "nb", "cs", "uk", "ru", "de", "fr", "es", "et", "ja", "zh-Hans")
    for lang, c in it.coverage().items():
        assert c["translated"] == c["total"] and c["stale"] == 0, lang
        assert c["machine"] + c["reviewed"] == c["translated"], lang
    raw = i18n.raw_catalogue("de")
    assert raw["@honesty.attribution"]["x-review"] in ("machine", "reviewed")
    assert raw["@honesty.attribution"]["x-source"] == i18n.source_hash(i18n.raw_catalogue("en")["honesty.attribution"])


def test_the_english_honesty_lines_are_exact():
    en = i18n.messages("en")
    assert en["honesty.attribution"] == ATTRIBUTION_EN
    assert en["honesty.none_confirmed"] == "None is a confirmed planet until independent follow-up confirms it."
    assert en["honesty.tess_pointing"] == "Pointing from the published schedule, not live telemetry"
    assert {en[k] for k in ("label.real", "label.model", "label.art", "label.illustration")} == {
        "Real data, cited", "Model from stored values", "Artist's impression", "Illustration"}
    assert "SuperIntelligence" not in json.dumps(i18n.raw_catalogue("en"))


def test_every_caveat_survives_in_every_language_and_the_embargo_line_has_no_number():
    for lang in i18n.TRANSLATIONS:
        msgs = i18n.messages(lang)
        for mid, words in it.CAVEATS.items():
            assert msgs.get(mid, "").strip(), (lang, mid)
            assert all(w in msgs[mid] for w in words), (lang, mid)
        assert not re.search(r"\d", msgs["honesty.embargo"]), lang
        assert "TRANSLATING.md" in msgs["i18n.mtnote"] and "TRANSLATING.md" in msgs["i18n.picker.note"], lang


def test_a_missing_or_stale_caveat_is_a_failure_and_a_missing_string_falls_back_to_english(monkeypatch):
    usable = i18n.messages
    monkeypatch.setattr(i18n, "messages", lambda lang: {k: v for k, v in usable(lang).items() if k != "honesty.none_confirmed"})
    assert "de honesty.none_confirmed: the caveat is missing, empty or stale" in it.check(["de"])
    monkeypatch.setattr(i18n, "messages", usable)
    assert it.check_message("de", "honesty.embargo", "Held for review.", "Zurückgehalten für 3 Tage.")
    with i18n.use("de"):
        assert i18n.t("no.such.id", "Plain English") == "Plain English"


def test_the_checks_catch_placeholders_plurals_markup_brands_and_claims():
    bad = it.check_message("pl", "x", "{n, plural, one {# dip} other {# dips}}", "{n, plural, one {# spadek} other {# spadków}}")
    assert any("plural" in p for p in bad)
    assert it.check_message("de", "x", "Run {run}", "Lauf {lauf}")
    assert it.check_message("de", "x", "<b>No</b> image", "<b>Kein Bild")
    assert it.check_message("de", "x", "The Sentinels", "Die Wächter")
    assert it.check_message("de", "x", "A candidate dip.", "Ein entdeckter Kandidat.")
    assert it.check_message("de", "x", "A candidate dip.", "Ein Kandidat.") == []


# ---------- the message format ----------
@pytest.mark.parametrize("lang,n,cat", [("en", 1, "one"), ("en", 2, "other"), ("pl", 1, "one"), ("pl", 3, "few"), ("pl", 5, "many"),
                                        ("pl", 22, "few"), ("pl", 12, "many"), ("pl", 1.5, "other"), ("cs", 4, "few"), ("cs", 5, "other"),
                                        ("cs", 1.5, "many"), ("ru", 21, "one"), ("ru", 11, "many"), ("uk", 3, "few"), ("fr", 0, "one"),
                                        ("fr", 1000000, "many"), ("ja", 1, "other"), ("zh-Hans", 2, "other")])
def test_cldr_plural_categories(lang, n, cat):
    assert i18n.plural_category(lang, n) == cat


def test_numbers_dates_and_messages_per_locale():
    assert i18n.format_number(1234567.5, "en", 1) == "1,234,567.5"
    assert i18n.format_number(1234567.5, "de", 1) == "1.234.567,5"
    assert i18n.format_number(1234.5, "fr", 1) == "1\u202f234,5"
    assert i18n.format_percent(0.5, "fr") == "50\xa0%" and i18n.format_percent(0.5, "en") == "50%"
    assert i18n.format_date("2026-10-24", "en") == "2026-10-24" and i18n.format_date("2026-10-24", "de") == "24.10.2026"
    msg = "{n, plural, one {# dip} few {# spadki} many {# spadków} other {# spadku}}"
    assert i18n.format_message(msg, {"n": 5}, "pl") == "5 spadków"
    assert i18n.format_message("It''s {x}", {"x": "<b>"}, "en", html=True) == "It's &lt;b&gt;"
    assert i18n.format_message("'{literal}' {n, number}", {"n": 12345}, "de") == "{literal} 12.345"


def test_the_browser_twin_formats_as_python_does():
    if not __import__("shutil").which("node"):
        pytest.skip("node is not installed")
    js = i18n.SHELL_JS
    assert "SetuI18n" in js
    msgs = ["{n, plural, one {# spadek} few {# spadki} many {# spadków} other {# spadku}}", "{n, number} · {d, date}", "It''s {x}"]
    cases = [("pl", {"n": 22, "d": "2026-10-24", "x": "y"}), ("de", {"n": 12345, "d": "2026-10-24", "x": "y"}), ("ja", {"n": 3, "d": "2026-10-24", "x": "y"})]
    probe = ("globalThis.window = globalThis; globalThis.document = {documentElement: {lang: 'en'}, addEventListener(){}, "
             "querySelectorAll(){ return []; }, querySelector(){ return null; }}; globalThis.I18N_CONF = {locales: ['en', 'pl', 'de', 'ja'], names: {}, cats: {}, pages: []};\n" + js
             + f"\nconst M = {json.dumps(msgs)}, C = {json.dumps(cases)};\n"
             "console.log(JSON.stringify(C.map(([l, a]) => M.map(m => SetuI18n.fmt(m, a, l)))));")
    out = subprocess.run(["node", "-e", probe], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [[i18n.format_message(m, a, lang) for m in msgs] for lang, a in cases]


# ---------- the tool's language ----------
def test_the_tool_picks_its_language_from_the_flag_then_the_environment():
    assert i18n.resolve_lang(None, {}) == "en"
    assert i18n.resolve_lang(None, {"LANG": "de_DE.UTF-8"}) == "de"
    assert i18n.resolve_lang(None, {"LANG": "de_DE.UTF-8", "LC_ALL": "fr_FR.UTF-8"}) == "fr"
    assert i18n.resolve_lang(None, {"SETUHQ_LANG": "ja", "LANG": "de_DE.UTF-8"}) == "ja"
    assert i18n.resolve_lang("uk", {"SETUHQ_LANG": "ja"}) == "uk"
    assert i18n.resolve_lang("xx", {"LANG": "de_DE.UTF-8"}) == "en"  # asked for and unsupported: English
    assert i18n.resolve_lang(None, {"LANG": "zh_CN.UTF-8"}) == "zh-Hans" and i18n.resolve_lang(None, {"LANG": "zh_TW"}) == "en"
    assert i18n.resolve_lang(None, {"LANG": "no_NO"}) == "nb" and i18n.resolve_lang(None, {"LANG": "C.UTF-8"}) == "en"


def test_cli_help_and_output_in_german_with_english_files(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "SETUHQ_LANG": "en", "PYTHONPATH": str(ROOT / "src")}
    de = subprocess.run([sys.executable, "-m", "setuhq.cli", "--lang", "de", "--help"], capture_output=True, text=True, env=env, cwd=ROOT)
    en = subprocess.run([sys.executable, "-m", "setuhq.cli", "--help"], capture_output=True, text=True, env=env, cwd=ROOT)
    assert de.returncode == 0 and en.returncode == 0
    assert "Sprache der Ausgabe" in de.stdout and "language of the output" in en.stdout
    assert "--lang" in de.stdout and "setuhq" in de.stdout


def test_mcp_tool_descriptions_and_honesty_labels_localise():
    from setuhq.tools import TOOLS

    fn = TOOLS[0][0]
    name = fn.__name__
    doc = it.cleandoc(fn.__doc__ or "")
    with i18n.use("en"):
        assert it.tool_description(name, fn.__doc__) == doc
    with i18n.use("de"):
        assert it.tool_description(name, fn.__doc__) != doc
        assert "Sentinels" in i18n.tr("mcp.honesty.panel") and "Claude" in i18n.tr("mcp.honesty.panel")


def test_translation_memory_is_current():
    assert (ROOT / "docs/i18n/memory.tmx").read_text(encoding="utf-8") == it.memory_tmx()


def test_glossaries_name_the_brands_and_the_claim_words():
    for lang in i18n.TRANSLATIONS:
        g = it.glossary(lang)
        assert {"SetuHQ", "Sentinels", "Probes", "TESS", "CHEOPS", "ESA", "NASA", "TOI"} <= set(g["keep"]), lang
        assert "confirm" in g["claims"], lang
        assert {t["term_en"].split(" (")[0] for t in g["terms"]} >= {"transit", "light curve", "candidate", "flagged", "rejected"}, lang


# ---------- the built site ----------
@pytest.fixture(scope="module")
def site(pi_men_app):
    return Path(pi_men_app).parent


def test_main_pages_have_an_address_per_language_with_alternates(site):
    from setuhq.site import MAIN_PATHS

    home = (site / "index.html").read_text()
    de = (site / "de" / "explore" / "index.html").read_text()
    assert '<html lang="en"' in home and '<html lang="de"' in de
    assert 'rel="canonical" href="https://setuhq.com/de/explore/"' in de
    alts = re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', de)
    assert {h for h, _ in alts} == {"en", "x-default", *i18n.TRANSLATIONS}
    assert ("en", "https://setuhq.com/explore/") in alts and ("ja", "https://setuhq.com/ja/explore/") in alts
    for lang in i18n.TRANSLATIONS:
        assert (site / lang / "index.html").is_file(), lang
        sm = (site / f"sitemap-lang-{lang}.xml").read_text()
        assert sm.count("<loc>") == len(MAIN_PATHS) and f"https://setuhq.com/{lang}/" in sm
        assert f"sitemap-lang-{lang}.xml" in (site / "sitemap.xml").read_text()


def test_the_language_pages_carry_the_machine_note_and_keep_the_caveats(site):
    for lang in i18n.TRANSLATIONS:
        page = (site / lang / "index.html").read_text()
        msgs = i18n.messages(lang)
        assert i18n.format_message(msgs["honesty.footer"], {}, lang, html=True) in page.replace("&#x27;", "'").replace("&quot;", '"') or "honesty.footer" in page
        assert 'class="mtnote"' in page and "TRANSLATING.md" in page, lang
        assert 'href="/' + lang + '/explore/"' in page, lang
    home_de = (site / "de" / "index.html").read_text()
    assert "Kandidat" in home_de and "SetuHQ" in home_de


def test_english_keyed_text_is_its_message_and_the_page_unchanged_but_for_keys(site):
    assert it.site_mismatches(site) == []
    home = (site / "index.html").read_text()
    assert 'class="mtnote"' in home and ' hidden>' in home.split('class="mtnote"', 1)[1][:200]


def test_the_assets_keep_their_budgets_and_the_catalogues_stay_out_of_the_script(site):
    from setuhq.site import check_budget

    assert check_budget(site) == []
    app = next(site.glob("assets/app-*.js")).read_text()
    assert "Sentinels laufen" not in app and "/*" not in app.split("\n", 3)[-1][:2000]
    for lang in i18n.TRANSLATIONS:
        cat = json.loads(next(site.glob(f"assets/i18n/{lang}-*.json")).read_text())
        assert not any(k.startswith(("cli.", "mcp.")) for k in cat) and cat["honesty.attribution"], lang
    home = (site / "index.html").read_text()
    assert len(home) <= 90_000 and "Sentinels laufen" not in home


def test_stubs_stay_single_url_and_load_the_language_from_the_shell(site):
    tpl = (site / "assets" / "stub-template.html").read_text()
    assert "data-chrome" in tpl and "hreflang" not in tpl and "i18n-" not in tpl  # one address; the shell fetches the rest
    shell = next(site.glob("assets/site-*.js")).read_text()
    i18n_js = next(site.glob("assets/i18n-*.js")).name
    assert f"/assets/{i18n_js}" in shell and "setuhq-lang" in (site / "assets" / i18n_js).read_text()
    assert not (site / "de" / "planets").exists()


def test_minify_keeps_strings_and_regexes():
    from setuhq.minify import strip_css, strip_js

    js = "const a = 'x // y'; /* gone */ const r = /\\/\\*not a comment/; // gone too\nconst b = `/* kept */`;\n"
    out = strip_js(js)
    assert "gone" not in out and "'x // y'" in out and "/\\/\\*not a comment/" in out and "`/* kept */`" in out
    assert strip_css("a{color:red} /* c */\n  b{content:'/* k */'}\n") == "a{color:red}\nb{content:'/* k */'}\n"

<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Translating SetuHQ

SetuHQ's website and command-line tool speak 17 languages: English (the source) and Dutch (`nl`), Polish (`pl`),
Portuguese (`pt`), Finnish (`fi`), Swedish (`sv`), Danish (`da`), Norwegian Bokmål (`nb`), Czech (`cs`),
Ukrainian (`uk`), Russian (`ru`), German (`de`), French (`fr`), Spanish (`es`), Estonian (`et`), Japanese (`ja`)
and Simplified Chinese (`zh-Hans`).

**Every translation is machine-assisted and has not yet been reviewed by a native speaker.** Every string is marked
`machine` in its catalogue, and each language's language picker and page footer say so and link here. Corrections
from native speakers, especially astronomers, are the most useful contribution you can make: see
[Reviewing a translation](#reviewing-a-translation).

## Where the text lives

| File | What it holds |
| --- | --- |
| `src/setuhq/locales/en.arb` | The English catalogue: every message the site, the CLI, its reports and the MCP server show, with a stable id, a note for translators (`description`), its placeholders and the source file that uses it (`x-file`). Generated from the code; never edit it by hand. |
| `src/setuhq/locales/<lang>.arb` | One language: the translation of each id, with `x-review` (`machine` or `reviewed`) and `x-source` (a hash of the English it translates). |
| `docs/i18n/glossary.<lang>.json` | The language's fixed terms (transit, light curve, candidate, flagged, rejected, false positive, confirmed), the brand names that never translate, and its words for *discover* and *confirm*. |
| `src/setuhq/locales/js-templates.json` | The text the page scripts draw (written by `tools/i18n_harvest.mjs`), which `extract` adds to en.arb as `js.*` messages. |
| `docs/i18n/memory.tmx` | The translation memory: every current translation beside its English, as TMX 1.4, each unit with its id and review status. |

The catalogues are [ARB](https://github.com/google/app-resource-bundle) (JSON) files, which
[Weblate](https://weblate.org) reads and writes directly: add a component with the file format *ARB file*, the
file mask `src/setuhq/locales/*.arb` and the monolingual base `src/setuhq/locales/en.arb`. The TMX file imports into
Weblate's translation memory or any CAT tool.

## The message format

Messages are [ICU MessageFormat](https://unicode-org.github.io/icu/userguide/format_parse/messages/) with CLDR plural
rules:

```
{n, plural, one {# dip} other {# dips}} you can open
```

* **Plurals.** Give every plural category your language has, and only those: `one` and `other` for nl, fi, sv,
  da, nb, de, et; `one`, `many`, `other` for pt, fr, es; `one`, `few`, `many`, `other` for pl, cs, uk, ru; `other`
  alone for ja and zh-Hans. Exact matches (`=1 {...}`) are allowed in addition. `#` is the number, formatted for your
  language.
* **Placeholders** (`{run}`, `{n, number}`, `{date, date}`) must all stay, spelled exactly as in English. Numbers and
  dates are formatted per language (decimal mark, grouping, numeric date order) by the code, not by you.
* **Apostrophes.** A single `'` is ordinary text. `'{'` quotes a literal brace; `''` is one apostrophe.
* **Markup.** Keep every tag (`<b>`, `<a href="...">`, `<code>`) the English has, with the same attributes. Links
  stay as they are.
* **CLI help** keeps argparse's `%(prog)s`-style placeholders and `%%`.

## The rules every translation follows

These are checked by `python tools/i18n.py check` (and by the test suite and `scripts/ci_local.sh`); a translation
that breaks one is a failure, and the site and tool show English for that string until it is fixed.

1. **Brand and mission names never translate**: SetuHQ, Sentinels, Probes, TESS, CHEOPS, ESA, NASA, TOI, MAST,
   Claude, Anthropic, MCP.
2. **Glossary terms**: where the English has a glossary term, the translation uses the glossary's word for it.
3. **Never a stronger claim.** Write in a plain scientific tone. A translation may use its language's words for
   *discover* or *confirm* only where the English does; SetuHQ's own results are candidates, never confirmed or
   discovered. Japanese uses 検出 or 見つかる for *found*; Chinese uses 找到 or 检出.
4. **Every honesty caveat survives**, complete and in meaning: the attribution, *Probes only*, *None is a confirmed
   planet until independent follow-up confirms it*, the feed's embargo line (which never carries a number or a date),
   the CHEOPS disclaimer (ESA, CHEOPS and SetuHQ named exactly), the transients *search aid* line, *Pointing from the
   published schedule, not live telemetry*, and the five picture labels (Real data, cited · Model from stored values ·
   Artist's impression · Illustration · Speculative model). A missing or empty caveat is a failure.
5. **ESA's names and credits stay exact.** Programme PI names appear only in ESA's required credit lines, which are
   data and are not translated.
6. **What stays English**: file formats, JSON keys, configuration keys, the run manifest, the catalogue and every
   field a machine reads. The English attribution sentence is fixed: *Sentinels run on Claude (Anthropic) by default;
   other providers are supported and labelled. Probes are deterministic matched-filter detectors.*

## Reviewing a translation

1. Read your language's pages (`https://setuhq.com/<lang>/`) or run the tool with `--lang <lang>`.
2. Edit the string in `src/setuhq/locales/<lang>.arb` (or in Weblate) and set its `x-review` to `reviewed`.
3. Run `python tools/i18n.py sync <lang>` (refreshes `x-source` and the order), `python tools/i18n.py check` and
   `python tools/i18n.py tm` (the memory), then open a pull request.

When the English of a message changes, every translation of it becomes **stale** (its `x-source` no longer matches)
and falls back to English until someone translates it again. `python tools/i18n.py coverage` lists the stale strings
per language.

## Adding or changing English text

Text that people read is written in the code through the helpers in `setuhq.i18n`: `t("id", "English")` (plain
text), `th(...)` (text with markup), `span(...)`, `N_(...)` (a constant), `lk(label)` for a picture label, and in the
page scripts `T('id', 'English', {args})`. Elements carry their message as `data-i18n="id"` (and
`data-i18n-args`, `data-i18n-attr="aria-label:id"`), so the same English markup is localised on the server for the
`/<lang>/` pages and in the browser for everything else. After changing English text:

```
python tools/i18n.py extract     # rewrites src/setuhq/locales/en.arb from the code
python tools/i18n.py sync        # orders every language as the source; changed English is now stale
python tools/i18n.py check
python tools/i18n.py tm
```

The worked examples' editorial lines (their kind, summary, caveat, why and outcome in
`docs/results/showcase.json`) are extracted too, as `showcase.<run>.<field>`; changing that file makes them stale.

A message id is permanent: change the English under the same id when the meaning is the same, and use a new id
when it is not.

## Page text

The long-form prose of the main pages (the *How it works* chapters, the evidence write-ups, the docs pages, the
galaxy's explanations) and the text the page scripts compute have no hand-written id. Each block of it (a
paragraph, list item, heading, caption or table cell whose content is text and inline markup only, with no
`data-i18n` of its own) is a message whose id is a hash of its template:

* numbers in the text become `{n0}`, `{n1}`, … (shown in the reader's number format, except years, counts without a
  group separator, versions and licences), so a count that changes keeps the message and its translations;
* in text the scripts draw, the page's names (its heading, planet and star links) become `{s0}`, `{s1}`, …;
* inline markup (links, `<b>`, `<code>`) stays in the message with its attributes, and every translation keeps it.

`pg.*` messages are the blocks of the committed English main pages (`site/`), collected by `extract` and written
in their language when the `/<lang>/` pages are built (`setuhq.i18n_auto`). `js.*` messages are what the scripts
draw, collected by `node tools/i18n_harvest.mjs --site <a built site with stubs>` into
`src/setuhq/locales/js-templates.json` and put in place in the browser (`assets/i18n-auto-*.js`, loaded on
non-English pages only). When the English of a block changes, its id changes: the old translation is no longer used
and the block is English until it is translated again. On a `/<lang>/` page an in-app link to another page loads
it from the server, so the page's prose is always the server's.

Japanese and Chinese headings break only between phrases: they are set with `word-break: keep-all`, and
`python tools/i18n.py phrases --site site` puts `<wbr>` between the phrases of every heading message (BudouX for
Japanese, jieba and the glossary for Chinese; `pip install budoux jieba`, a tool dependency, never the site's).
The markup check ignores `<wbr>`; run `phrases` again after translating a heading.

## How a language is chosen

**Website.** The main pages (the five sections, their views and the fifteen *How it works* chapters) have an address
per language: English at `/`, every other language at `/<lang>/…` (`/de/explore/`, `/ja/how-it-works/transit/`),
each with `<html lang>`, a canonical link, hreflang alternates for every language and an entry in
`sitemap-lang-<lang>.xml`. The ~14,000 planet and star pages, the dip pages, case files, plates and run reports keep
one address and are localised in the browser from the catalogue of the language you chose. The language picker in
the top bar remembers your choice in your browser (`localStorage`, if it is allowed). On a first visit, if your
browser's language is one of the 16, a small dismissible bar offers it; the site never redirects you.

**Tool.** `setuhq --lang <lang> …` (and `setuhq-mcp --lang <lang>`), else `SETUHQ_LANG`, else `LC_ALL`,
`LC_MESSAGES` or `LANG` (`de_DE.UTF-8` → German, `zh_CN` → Simplified Chinese, `no` → Bokmål), else English. An
explicit `--lang` or `SETUHQ_LANG` that is not supported gives English. The language covers the CLI's messages and
help, the reports, dashboard, plates and case files it writes, and the MCP server's tool descriptions, instructions
and honesty labels. Files, JSON and every machine-read field stay English.

## What is still English

Data (planet and star names, catalogue values, references, stored error messages, the panel's own words), code,
commands and file paths, and a block whose English changed since it was translated. `python tools/i18n.py coverage
--site site` reports, per language, the share of each language's page text that is not English left in place.

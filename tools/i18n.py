#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The message catalogues (docs/TRANSLATING.md).

    python tools/i18n.py extract [--check]   # the code's messages into src/setuhq/locales/en.arb
    python tools/i18n.py sync [LANG ...]     # each translation ordered as the source, with x-review and x-source
    python tools/i18n.py check               # placeholders, plurals, markup, glossary, brand names, caveats
    python tools/i18n.py coverage [--site site]   # messages translated per language (and its pages' text)
    python tools/i18n.py phrases [--site site]   # <wbr> between the phrases of Japanese and Chinese headings
    python tools/i18n.py tm [--check]        # the translation memory, docs/i18n/memory.tmx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from setuhq import i18n  # noqa: E402
from setuhq import i18n_tools as it  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("--check", action="store_true", help="fail when en.arb is not what the code declares")
    sy = sub.add_parser("sync")
    sy.add_argument("langs", nargs="*")
    sy.add_argument("--check", action="store_true")
    sub.add_parser("check")
    cv = sub.add_parser("coverage")
    cv.add_argument("--site", help="also measure the text of each language's pages in this built site")
    ph = sub.add_parser("phrases", help="<wbr> between the phrases of every Japanese and Chinese heading")
    ph.add_argument("--site", default="site")
    tm = sub.add_parser("tm")
    tm.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "extract":
        text = it.dumps(it.extract())
        path = i18n.catalogue_path("en")
        if a.check:
            # Page text (pg.*) follows the committed site, which data updates change between extractions: only the
            # messages the code declares must be current.
            have = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if it.dumps(it.code_part(have)) != it.dumps(it.code_part(it.extract(pages=False))):
                print("src/setuhq/locales/en.arb is out of date: run python tools/i18n.py extract", file=sys.stderr)
                return 1
            print("en.arb is current")
            return 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        i18n.reload()
        print(f"{path.relative_to(it.ROOT)}: {sum(1 for k in it.extract() if not k.startswith('@'))} messages")
        return 0
    if a.cmd == "sync":
        bad = 0
        for lang in a.langs or i18n.TRANSLATIONS:
            text = it.dumps(it.sync(lang))
            path = i18n.catalogue_path(lang)
            if a.check:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    print(f"{lang}.arb is not in shape: run python tools/i18n.py sync {lang}", file=sys.stderr)
                    bad = 1
                continue
            path.write_text(text, encoding="utf-8")
        i18n.reload()
        return bad
    if a.cmd == "check":
        probs = it.check()
        for p in probs:
            print(p)
        print(f"{len(probs)} problem(s)" if probs else "every translation passes")
        return 1 if probs else 0
    if a.cmd == "coverage":
        cov = it.coverage()
        pages = it.page_coverage(a.site) if a.site else {}
        print(f"{'lang':8} {'messages':>14} {'%':>6} {'stale':>6} {'machine':>8} {'reviewed':>9}" + ("  page text" if pages else ""))
        for lang, c in cov.items():
            print(f"{lang:8} {c['translated']:>6} / {c['total']:<6} {c['percent']:>6} {c['stale']:>6} {c['machine']:>8} {c['reviewed']:>9}"
                  + (f"  {pages.get(lang, 0):>6}%" if pages else ""))
        return 0
    if a.cmd == "phrases":
        for lang, n in it.add_phrases(a.site).items():
            print(f"{lang}: {n} heading(s) with phrase breaks")
        return 0
    if a.cmd == "tm":
        text = it.memory_tmx()
        if a.check:
            if not it.TMX_PATH.is_file() or it.TMX_PATH.read_text(encoding="utf-8") != text:
                print("docs/i18n/memory.tmx is out of date: run python tools/i18n.py tm", file=sys.stderr)
                return 1
            print("memory.tmx is current")
            return 0
        it.TMX_PATH.parent.mkdir(parents=True, exist_ok=True)
        it.TMX_PATH.write_text(text, encoding="utf-8")
        print(f"{it.TMX_PATH.relative_to(it.ROOT)} written")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

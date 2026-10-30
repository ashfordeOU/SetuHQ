# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Localisation: one set of message catalogues for the site, the CLI, the outputs and the MCP server.

* **Catalogues.** ``src/setuhq/locales/<lang>.arb``: Application Resource Bundle files (JSON, read by Weblate), one
  per language. ``en.arb`` is the source, extracted from the code by ``tools/i18n.py extract`` (never edited by
  hand): each message has a stable id, its English text and, in ``@<id>``, a translator comment
  (``description``) and its placeholders. A translation's ``@<id>`` holds its review status (``x-review``:
  ``machine`` or ``reviewed``) and the hash of the English it translates (``x-source``); a translation whose English
  has changed since is stale and is not used (English shows until it is updated).
* **Messages** are ICU MessageFormat: ``{name}``, ``{n, number}``, ``{n, number, integer}``, ``{n, number, ::.00}``,
  ``{n, number, percent}``, ``{d, date}``, ``{n, plural, one {# day} other {# days}}`` (CLDR plural rules for every
  language here: Polish, Czech, Ukrainian and Russian have few and many; Japanese and Chinese only other) and
  ``{x, select, a {...} other {...}}``. Messages shown on pages are HTML fragments; an argument is escaped where it
  is put into HTML.
* **Pages** are localised by key, as Fluent's DOM bindings do: an element carries ``data-i18n="<id>"`` (and
  ``data-i18n-args`` with its arguments as JSON), or ``data-i18n-attr="aria-label:<id>|title:<id>"``, around its
  English text. :func:`localize_html` fills them in at build time for the pages under ``/<lang>/``; the shell's script
  does the same in the browser for the pages that keep one address (the catalogue's planets and stars, the dips, the
  case files, the reports) and for every view the app draws.
* **The tool** picks its language from ``--lang``, then ``SETUHQ_LANG``, then ``LC_ALL``, ``LC_MESSAGES`` and
  ``LANG``, else English (:func:`resolve_lang`). Only human-facing text changes: JSON keys, config keys, file formats,
  manifests and every machine-read field stay English.

Standard library only.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import html as _html
import json
import os
import re
from functools import lru_cache
from pathlib import Path

SOURCE = "en"
# English first, then the sixteen translations in the order the language picker lists them.
LOCALES = ("en", "nl", "pl", "pt", "fi", "sv", "da", "nb", "cs", "uk", "ru", "de", "fr", "es", "et", "ja", "zh-Hans")
TRANSLATIONS = LOCALES[1:]
# Each language's own name, as the picker shows it.
NATIVE = {"en": "English", "nl": "Nederlands", "pl": "Polski", "pt": "Português", "fi": "Suomi", "sv": "Svenska",
          "da": "Dansk", "nb": "Norsk bokmål", "cs": "Čeština", "uk": "Українська", "ru": "Русский", "de": "Deutsch",
          "fr": "Français", "es": "Español", "et": "Eesti", "ja": "日本語", "zh-Hans": "简体中文"}
# Open Graph's locale for each (og:locale).
OG_LOCALE = {"en": "en_GB", "nl": "nl_NL", "pl": "pl_PL", "pt": "pt_BR", "fi": "fi_FI", "sv": "sv_SE", "da": "da_DK",
             "nb": "nb_NO", "cs": "cs_CZ", "uk": "uk_UA", "ru": "ru_RU", "de": "de_DE", "fr": "fr_FR", "es": "es_ES",
             "et": "et_EE", "ja": "ja_JP", "zh-Hans": "zh_CN"}
LOCALE_DIR = Path(__file__).resolve().parent / "locales"
TRANSLATING_URL = "https://github.com/ashfordeOU/SetuHQ/blob/main/docs/TRANSLATING.md"
STORAGE_KEY = "setuhq-lang"

_CURRENT: contextvars.ContextVar[str] = contextvars.ContextVar("setuhq_lang", default=SOURCE)


# ---------------------------------------------------------------------------------------------------------------
# Choosing the language
# ---------------------------------------------------------------------------------------------------------------

def normalise(tag: str | None) -> str | None:
    """A supported language for a POSIX locale or BCP 47 tag ('de_DE.UTF-8', 'pt-BR', 'zh_CN', 'no'), else None."""
    if not tag:
        return None
    t = str(tag).split(".")[0].split("@")[0].replace("_", "-").strip()
    if not t or t in ("C", "POSIX"):
        return None
    low = t.lower()
    if low.startswith("zh"):
        return None if ("hant" in low or low.endswith(("-tw", "-hk", "-mo"))) else "zh-Hans"
    base = low.split("-")[0]
    if base in ("no", "nn"):
        return "nb"
    return base if base in LOCALES else None


def resolve_lang(explicit: str | None = None, environ: dict | None = None) -> str:
    """The language for the tool's output: ``--lang``, then SETUHQ_LANG, then LC_ALL, LC_MESSAGES and LANG; English
    when none names a supported language. An explicit unsupported value falls back to English too."""
    env = os.environ if environ is None else environ
    for value in (explicit, env.get("SETUHQ_LANG"), env.get("LC_ALL"), env.get("LC_MESSAGES"), env.get("LANG")):
        if value:
            lang = normalise(value)
            if lang:
                return lang
            if value is explicit or value == env.get("SETUHQ_LANG"):
                return SOURCE  # asked for, but not supported: English, not the next setting
    return SOURCE


def current() -> str:
    return _CURRENT.get()


def set_lang(lang: str | None) -> str:
    lang = normalise(lang) or SOURCE
    _CURRENT.set(lang)
    return lang


@contextlib.contextmanager
def use(lang: str | None):
    """Everything inside speaks ``lang`` (English for an unsupported one)."""
    token = _CURRENT.set(normalise(lang) or SOURCE)
    try:
        yield
    finally:
        _CURRENT.reset(token)


# ---------------------------------------------------------------------------------------------------------------
# CLDR plural rules (cardinal), number and date formatting
# ---------------------------------------------------------------------------------------------------------------

PLURAL_CATEGORIES = {
    **{lang: ("one", "other") for lang in ("en", "nl", "fi", "sv", "da", "nb", "de", "et")},
    "pl": ("one", "few", "many", "other"), "cs": ("one", "few", "many", "other"),
    "uk": ("one", "few", "many", "other"), "ru": ("one", "few", "many", "other"),
    "pt": ("one", "many", "other"), "fr": ("one", "many", "other"), "es": ("one", "many", "other"),
    "ja": ("other",), "zh-Hans": ("other",),
}


def _operands(n) -> tuple[float, int, int, int]:
    """CLDR operands n, i, v (visible fraction digits) and f, from a number as it would be written."""
    s = repr(float(n)) if isinstance(n, float) else str(n)
    s = s.lstrip("-")
    if "e" in s or "E" in s:
        s = format(abs(float(n)), "f")
    if "." in s:
        whole, frac = s.split(".", 1)
        frac = frac.rstrip("0") if isinstance(n, float) and frac.strip("0") == "" else frac
        if isinstance(n, float) and float(n).is_integer():
            frac = ""
    else:
        whole, frac = s, ""
    return abs(float(n)), int(whole or 0), len(frac), int(frac or 0)


def plural_category(lang: str, n) -> str:
    """The CLDR cardinal plural category of ``n`` in ``lang``."""
    lang = lang if lang in PLURAL_CATEGORIES else SOURCE
    num, i, v, f = _operands(n)
    i10, i100 = i % 10, i % 100
    if lang in ("ja", "zh-Hans"):
        return "other"
    if lang in ("en", "nl", "fi", "sv", "nb", "de", "et"):
        return "one" if i == 1 and v == 0 else "other"
    if lang == "da":
        t = f
        return "one" if num == 1 or (t != 0 and i in (0, 1)) else "other"
    if lang == "pl":
        if i == 1 and v == 0:
            return "one"
        if v == 0 and 2 <= i10 <= 4 and not 12 <= i100 <= 14:
            return "few"
        if v == 0 and (i != 1 and i10 in (0, 1) or 5 <= i10 <= 9 or 12 <= i100 <= 14):
            return "many"
        return "other"
    if lang == "cs":
        if i == 1 and v == 0:
            return "one"
        if 2 <= i <= 4 and v == 0:
            return "few"
        return "many" if v != 0 else "other"
    if lang in ("uk", "ru"):
        if v == 0 and i10 == 1 and i100 != 11:
            return "one"
        if v == 0 and 2 <= i10 <= 4 and not 12 <= i100 <= 14:
            return "few"
        if v == 0 and (i10 == 0 or 5 <= i10 <= 9 or 11 <= i100 <= 14):
            return "many"
        return "other"
    # fr, es, pt: one, many (a multiple of a million), other
    if lang == "es":
        one = num == 1
    else:
        one = i in (0, 1)
    if one:
        return "one"
    if v == 0 and i != 0 and i % 1_000_000 == 0:
        return "many"
    return "other"


# Decimal mark, group separator, minimum grouping digits (CLDR), minus sign and percent pattern, per language.
NUMBERS = {
    "en": (".", ",", 1, "-", "{}%"), "nl": (",", ".", 1, "-", "{}%"), "pl": (",", " ", 2, "-", "{}%"),
    "pt": (",", ".", 1, "-", "{}%"), "fi": (",", " ", 1, "−", "{} %"), "sv": (",", " ", 1, "−", "{} %"),
    "da": (",", ".", 1, "-", "{} %"), "nb": (",", " ", 1, "−", "{} %"), "cs": (",", " ", 1, "-", "{} %"),
    "uk": (",", " ", 1, "-", "{}%"), "ru": (",", " ", 1, "-", "{} %"), "de": (",", ".", 1, "-", "{} %"),
    "fr": (",", " ", 1, "-", "{} %"), "es": (",", ".", 2, "-", "{} %"), "et": (",", " ", 2, "−", "{}%"),
    "ja": (".", ",", 1, "-", "{}%"), "zh-Hans": (".", ",", 1, "-", "{}%"),
}
# A date (from an ISO date) in each language's short numeric form; English keeps ISO 8601, as SetuHQ always wrote it.
DATES = {"en": "{y}-{m}-{d}", "nl": "{d}-{m}-{y}", "pl": "{d}.{m}.{y}", "pt": "{d}/{m}/{y}", "fi": "{D}.{M}.{y}",
         "sv": "{y}-{m}-{d}", "da": "{d}.{m}.{y}", "nb": "{d}.{m}.{y}", "cs": "{D}. {M}. {y}", "uk": "{d}.{m}.{y}",
         "ru": "{d}.{m}.{y}", "de": "{d}.{m}.{y}", "fr": "{d}/{m}/{y}", "es": "{D}/{M}/{y}", "et": "{D}.{m}.{y}",
         "ja": "{y}/{m}/{d}", "zh-Hans": "{y}/{m}/{d}"}


def format_number(x, lang: str | None = None, decimals: int | None = None, *, max_decimals: int = 3) -> str:
    """``x`` with the language's decimal mark and grouping: fixed ``decimals``, else up to ``max_decimals``."""
    lang = lang or current()
    dec, grp, min_group, minus, _ = NUMBERS.get(lang, NUMBERS[SOURCE])
    if decimals is None:
        s = f"{float(x):.{max_decimals}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(int(x))
    else:
        s = f"{float(x):.{decimals}f}"
    neg = s.startswith("-")
    s = s.lstrip("-")
    whole, _, frac = s.partition(".")
    if len(whole) >= 4 + (min_group - 1):
        parts = []
        while len(whole) > 3:
            parts.insert(0, whole[-3:])
            whole = whole[:-3]
        whole = grp.join([whole] + parts)
    out = whole + (dec + frac if frac else "")
    if neg and out.strip("0" + dec + grp) != "":
        out = minus + out
    return out


def format_percent(x, lang: str | None = None, decimals: int = 0) -> str:
    """A fraction (0.5) as a percentage ("50%", "50 %")."""
    lang = lang or current()
    return NUMBERS.get(lang, NUMBERS[SOURCE])[4].format(format_number(100 * float(x), lang, decimals))


def format_date(iso, lang: str | None = None) -> str:
    """An ISO date ('2026-10-24', or a timestamp that starts with one) in the language's numeric form."""
    lang = lang or current()
    s = str(iso or "")[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if not m:
        return s
    y, mo, d = m.groups()
    return DATES.get(lang, DATES[SOURCE]).format(y=y, m=mo, d=d, M=str(int(mo)), D=str(int(d)))


# ---------------------------------------------------------------------------------------------------------------
# ICU MessageFormat
# ---------------------------------------------------------------------------------------------------------------

class MessageError(ValueError):
    """A message that does not parse."""


def parse(msg: str):
    """A message as a list of parts: text, ('arg', name, type, style), ('plural'|'select', name, offset,
    {key: parts}) and ('#',). Apostrophes follow ICU's DOUBLE_OPTIONAL mode: '' is one apostrophe, and an
    apostrophe quotes only before {, }, # (in a plural) or |."""
    pos = 0

    def text(in_plural: bool, depth: int):
        nonlocal pos
        out, buf = [], []
        while pos < len(msg):
            c = msg[pos]
            if c == "'":
                nxt = msg[pos + 1] if pos + 1 < len(msg) else ""
                if nxt == "'":
                    buf.append("'")
                    pos += 2
                    continue
                if nxt and (nxt in "{}|" or (in_plural and nxt == "#")):
                    end = msg.find("'", pos + 1)
                    if end < 0:
                        raise MessageError(f"unterminated quote in {msg!r}")
                    buf.append(msg[pos + 1:end])
                    pos = end + 1
                    continue
                buf.append(c)
                pos += 1
                continue
            if c == "}":
                if depth == 0:
                    raise MessageError(f"unbalanced '}}' in {msg!r}")
                break
            if c == "#" and in_plural:
                if buf:
                    out.append("".join(buf))
                    buf = []
                out.append(("#",))
                pos += 1
                continue
            if c == "{":
                if buf:
                    out.append("".join(buf))
                    buf = []
                pos += 1
                out.append(argument(depth))
                continue
            buf.append(c)
            pos += 1
        if buf:
            out.append("".join(buf))
        return out

    def argument(depth: int):
        nonlocal pos
        m = re.compile(r"\s*([A-Za-z_][\w]*)\s*(?:,\s*([a-z]+)\s*)?").match(msg, pos)
        if not m or not m.group(1):
            raise MessageError(f"bad argument at {pos} in {msg!r}")
        name, kind = m.group(1), m.group(2)
        pos = m.end()
        if kind is None:
            if pos >= len(msg) or msg[pos] != "}":
                raise MessageError(f"expected '}}' at {pos} in {msg!r}")
            pos += 1
            return ("arg", name, None, None)
        if kind in ("number", "date"):
            end = msg.find("}", pos)
            if end < 0:
                raise MessageError(f"unterminated argument in {msg!r}")
            style = msg[pos:end].lstrip(",").strip() or None
            pos = end + 1
            return ("arg", name, kind, style)
        if kind not in ("plural", "select"):
            raise MessageError(f"unknown argument type {kind!r} in {msg!r}")
        if pos < len(msg) and msg[pos] == ",":
            pos += 1
        offset = 0
        mo = re.compile(r"\s*offset:\s*(\d+)").match(msg, pos)
        if mo:
            offset, pos = int(mo.group(1)), mo.end()
        branches = {}
        while True:
            mk = re.compile(r"\s*(=\d+|[\w-]+)\s*\{").match(msg, pos)
            if not mk:
                break
            pos = mk.end()
            body = text(kind == "plural", depth + 1)
            if pos >= len(msg) or msg[pos] != "}":
                raise MessageError(f"unterminated branch {mk.group(1)!r} in {msg!r}")
            pos += 1
            if mk.group(1) in branches:
                raise MessageError(f"duplicate branch {mk.group(1)!r} in {msg!r}")
            branches[mk.group(1)] = body
        ws = re.compile(r"\s*\}").match(msg, pos)
        if not ws:
            raise MessageError(f"expected '}}' after the branches at {pos} in {msg!r}")
        pos = ws.end()
        if "other" not in branches:
            raise MessageError(f"{kind} without an 'other' branch in {msg!r}")
        return (kind, name, offset, branches)

    parts = text(False, 0)
    if pos != len(msg):
        raise MessageError(f"unbalanced '}}' in {msg!r}")
    return parts


@lru_cache(maxsize=8192)
def _parsed(msg: str):
    return parse(msg)


def _number(v, style: str | None, lang: str) -> str:
    if style == "integer":
        return format_number(round(float(v)), lang)
    if style == "percent":
        return format_percent(v, lang)
    if style and style.startswith("::"):
        m = re.match(r"^::\s*\.(0*)$", style)
        if m:
            return format_number(v, lang, len(m.group(1)))
        if style.strip() == "::percent":
            return format_percent(v, lang)
    return format_number(v, lang)


def _fmt(parts, args: dict, lang: str, escape, n=None) -> str:
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif p[0] == "#":
            out.append(_number(n, None, lang) if n is not None else "#")
        elif p[0] == "arg":
            _, name, kind, style = p
            v = args.get(name, "{" + name + "}")
            if kind == "number" and name in args:
                out.append(_number(v, style, lang))
            elif kind == "date" and name in args:
                out.append(format_date(v, lang))
            else:
                out.append(escape(str(v)))
        else:
            kind, name, offset, branches = p
            v = args.get(name)
            if kind == "select":
                body = branches.get(str(v), branches["other"])
                out.append(_fmt(body, args, lang, escape, n))
                continue
            num = float(v) if v is not None else 0
            exact = f"={int(num)}" if num.is_integer() else None
            if exact in branches:
                body = branches[exact]
            else:
                val = v - offset if isinstance(v, (int, float)) else 0
                body = branches.get(plural_category(lang, val), branches["other"])
            nv = (v - offset) if isinstance(v, (int, float)) else v
            out.append(_fmt(body, args, lang, escape, nv))
    return "".join(out)


def format_message(msg: str, args: dict | None = None, lang: str | None = None, *, html: bool = False) -> str:
    """``msg`` formatted with ``args`` in ``lang``; with ``html`` each argument is HTML-escaped."""
    esc = (lambda s: _html.escape(s, quote=False)) if html else (lambda s: s)
    return _fmt(_parsed(msg), args or {}, lang or current(), esc)


def arguments(msg: str) -> set[str]:
    """Every argument a message names (its placeholders)."""
    names = set()

    def walk(parts):
        for p in parts:
            if isinstance(p, tuple) and p[0] in ("arg", "plural", "select"):
                names.add(p[1])
                if p[0] in ("plural", "select"):
                    for body in p[3].values():
                        walk(body)

    walk(parse(msg))
    return names


def plural_branches(msg: str) -> list[tuple[str, set[str]]]:
    """Each plural argument of a message with the branch keys it gives."""
    out = []

    def walk(parts):
        for p in parts:
            if isinstance(p, tuple) and p[0] in ("plural", "select"):
                if p[0] == "plural":
                    out.append((p[1], set(p[3])))
                for body in p[3].values():
                    walk(body)

    walk(parse(msg))
    return out


# ---------------------------------------------------------------------------------------------------------------
# The catalogues
# ---------------------------------------------------------------------------------------------------------------

def source_hash(text: str) -> str:
    """The short hash of an English message, kept with each translation (x-source) to tell when it went stale."""
    return hashlib.sha256(text.encode()).hexdigest()[:10]


def catalogue_path(lang: str) -> Path:
    return LOCALE_DIR / f"{lang}.arb"


@lru_cache(maxsize=None)
def raw_catalogue(lang: str) -> dict:
    """A language's ARB file as stored (messages and their @metadata); {} when it has none."""
    p = catalogue_path(lang)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def messages(lang: str) -> dict[str, str]:
    """A language's usable messages: for a translation, those whose English has not changed since (not stale) and
    that are not empty. English: every message."""
    return dict(_messages(lang))


@lru_cache(maxsize=None)
def _messages(lang: str) -> tuple:
    src = raw_catalogue(SOURCE)
    if lang == SOURCE:
        return tuple((k, v) for k, v in src.items() if not k.startswith("@"))
    cat = raw_catalogue(lang)
    out = []
    for k, v in cat.items():
        if k.startswith("@") or not isinstance(v, str) or not v.strip() or k not in src:
            continue
        meta = cat.get("@" + k) or {}
        if meta.get("x-source") and meta["x-source"] != source_hash(src[k]):
            continue  # stale: the English changed after this was translated
        out.append((k, v))
    return tuple(out)


def reload() -> None:
    """Forget the cached catalogues (after a tool rewrote them)."""
    raw_catalogue.cache_clear()
    _messages.cache_clear()


def lookup(msg_id: str, lang: str | None = None) -> str | None:
    lang = lang or current()
    hit = messages(lang).get(msg_id) if lang != SOURCE else None
    return hit if hit is not None else messages(SOURCE).get(msg_id)


def N_(msg_id: str, en: str, note: str | None = None) -> str:
    """Declare a message (for extraction) and give its English: for tables and constants built at import time."""
    return en


def t(msg_id: str, en: str, note: str | None = None, **args) -> str:
    """The message ``msg_id`` in the current language (its English ``en`` as written in the code when the language
    has no usable translation), formatted with ``args``. Plain text: arguments are not escaped."""
    lang = current()
    msg = en if lang == SOURCE else (messages(lang).get(msg_id) or en)
    return format_message(msg, args, lang) if (args or "{" in msg or "'" in msg) else msg


def th(msg_id: str, en: str, note: str | None = None, **args) -> str:
    """As :func:`t`, for HTML: each argument is escaped."""
    lang = current()
    msg = en if lang == SOURCE else (messages(lang).get(msg_id) or en)
    return format_message(msg, args, lang, html=True)


def tr(msg_id: str, fallback: str | None = None, **args) -> str:
    """A message declared elsewhere (by :func:`N_` or :func:`t`), looked up by id at run time."""
    msg = lookup(msg_id) or fallback or msg_id
    return format_message(msg, args, current()) if args or "{" in msg else msg


# The five figure labels (docs/SITE.md) and their messages.
LABEL_IDS = {"Real data, cited": "label.real", "Model from stored values": "label.model", "Artist's impression": "label.art",
             "Illustration": "label.illustration", "Speculative model": "label.speculative"}


def lk(label: str) -> str:
    """The key of a figure label's element (empty for anything that is not one of the five labels)."""
    return k(LABEL_IDS[label]) if label in LABEL_IDS else ""


def span(msg_id: str, en: str, note: str | None = None, **args) -> str:
    """The message as HTML in a keyed <span> (its arguments escaped), for text inside a larger element."""
    return f"<span{k(msg_id, **args)}>{th(msg_id, en, **_plain(args))}</span>"


def _plain(args: dict) -> dict:
    return {a: v for a, v in args.items() if not a.endswith("@")}


def k(msg_id: str, **args) -> str:
    """The attribute that keys an element's content to a message: ' data-i18n="id"' (and its arguments)."""
    out = f' data-i18n="{msg_id}"'
    if args:
        out += " data-i18n-args='" + _attr_json(args) + "'"
    return out


def kargs(**args) -> str:
    """Only the arguments attribute (for an element keyed by data-i18n-attr)."""
    return " data-i18n-args='" + _attr_json(args) + "'" if args else ""


def ka(**attrs: str) -> str:
    """The attribute that keys an element's attributes to messages: ka(aria_label="nav.open") gives
    ' data-i18n-attr="aria-label:nav.open"'."""
    return ' data-i18n-attr="' + "|".join(f"{a.replace('_', '-')}:{m}" for a, m in attrs.items()) + '"'


def _attr_json(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    return s.replace("&", "&amp;").replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------------------------------------------
# Localising a page by its keys
# ---------------------------------------------------------------------------------------------------------------

_TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>")
_ATTR = re.compile(r"""([^\s=>/]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?""")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def _attrs(s: str) -> list[tuple[str, str | None]]:
    out = []
    for m in _ATTR.finditer(s or ""):
        v = m.group(2)
        if v is not None and v[:1] in "\"'":
            v = v[1:-1]
        out.append((m.group(1), v))
    return out


def _close(src: str, tag: str, start: int) -> int:
    """Where the element opened just before ``start`` closes (the index of its end tag), counting nested ones."""
    depth, pat = 1, re.compile(rf"<(/?){tag}(?=[\s>/])", re.I)
    for m in pat.finditer(src, start):
        if m.group(1):
            depth -= 1
            if depth == 0:
                return m.start()
        else:
            end = src.find(">", m.end())
            if end > 0 and src[end - 1] != "/":
                depth += 1
    return -1


def _rebuild(tag: str, attrs: list, selfclose: str) -> str:
    def one(n, v):
        if v is None:
            return f" {n}"
        return f" {n}='{v}'" if '"' in v and "'" not in v else f' {n}="{v}"'
    return "<" + tag + "".join(one(n, v) for n, v in attrs) + (" /" if selfclose else "") + ">"


def localize_html(src: str, lang: str, *, link=None) -> str:
    """``src`` with every keyed element and attribute in ``lang`` (English where the language has no usable
    translation; the element is left as it is). ``link``, when given, rewrites each internal href (a function from
    the old href to the new)."""
    cat = messages(lang) if lang != SOURCE else {}
    out, pos = [], 0
    for m in _TAG.finditer(src):
        if m.start() < pos:
            continue
        tag, raw, selfclose = m.group(1), m.group(2) or "", m.group(3)
        if "data-i18n" not in raw and not (link and " href=" in raw):
            continue
        attrs = _attrs(raw)
        a = dict(attrs)
        args = {}
        if a.get("data-i18n-args"):
            try:
                args = json.loads(_html.unescape(a["data-i18n-args"]))
            except ValueError:
                args = {}
            for key in [x for x in args if x.endswith("@")]:
                if cat.get(args[key]):
                    args[key[:-1]] = format_message(cat[args[key]], {}, lang)
        new_attrs = []
        for name, value in attrs:
            if name == "href" and link and value is not None:
                value = link(value)
            new_attrs.append((name, value))
        if a.get("data-i18n-attr"):
            for spec in a["data-i18n-attr"].split("|"):
                an, _, mid = spec.partition(":")
                msg = cat.get(mid)
                if msg is None:
                    continue
                text = _html.escape(format_message(msg, args, lang), quote=True)
                new_attrs = [(n, text if n == an else v) for n, v in new_attrs]
        out.append(src[pos:m.start()])
        out.append(_rebuild(tag, new_attrs, selfclose) if new_attrs != attrs else m.group(0))
        pos = m.end()
        mid = a.get("data-i18n")
        if mid and not selfclose and tag.lower() not in VOID:
            end = _close(src, tag, m.end())
            if end < 0:
                continue
            msg = cat.get(mid)
            if msg is not None:
                inner = format_message(msg, args, lang, html=True)
                if link:
                    inner = re.sub(r'href="([^"]*)"', lambda h: f'href="{link(h.group(1))}"', inner)
                out.append(inner)
                pos = end
    out.append(src[pos:])
    return "".join(out)


def localize_output(src: str) -> str:
    """A page the tool writes (a report, the plates, a case file, the dashboard) in the current language: its keyed
    text, and its lang attribute. English: unchanged."""
    lang = current()
    if lang == SOURCE:
        return src
    out = localize_html(src, lang)
    return re.sub(r"""<html lang=(['"])en\1""", lambda m: f"<html lang={m.group(1)}{lang}{m.group(1)}", out, count=1)


def keyed_ids(src: str) -> set[str]:
    """Every message id a page's markup or script keys (data-i18n, data-i18n-attr)."""
    ids = set(re.findall(r'data-i18n="([\w.-]+)"', src))
    for spec in re.findall(r'data-i18n-attr="([^"]+)"', src):
        ids.update(p.partition(":")[2] for p in spec.split("|"))
    return ids


_KEY_ATTRS = re.compile(r""" data-i18n(?:-attr|-args)?=(?:"[^"]*"|'[^']*')| data-i18n-auto(?=[\s>])""")


def unkey(src: str) -> str:
    """Markup without its localisation keys: what the page says and how it is built, for a reader (or a test) that
    compares the English markup as it was before the keys."""
    return _KEY_ATTRS.sub("", src)


def client_catalogue(lang: str) -> dict[str, str]:
    """What a page's script loads for ``lang``: every usable message the site and its pages use (not the CLI's or
    the MCP server's)."""
    return {k: v for k, v in sorted(messages(lang).items()) if not k.startswith(("cli.", "mcp.", "pg.", "js."))}


def section(path: str) -> str:
    """The part of the site a page belongs to, for the text its scripts draw: its first folder ("home" for /)."""
    seg = [x for x in path.split("/") if x]
    if seg and seg[0] in TRANSLATIONS:
        seg = seg[1:]
    return seg[0] if seg else "home"


def js_catalogues(lang: str) -> dict[str, dict[str, str]]:
    """The translations of the text the page scripts draw (js.*, src/setuhq/locales/js-templates.json), one
    catalogue per part of the site (``section``), so that a page loads only its own part's."""
    drawn = Path(__file__).parent / "locales" / "js-templates.json"
    if not drawn.is_file():
        return {}
    usable, out = messages(lang), {}
    for mid, d in sorted(json.loads(drawn.read_text(encoding="utf-8")).items()):
        if mid in usable:
            for sec in {section(p) for p in d["pages"]}:
                out.setdefault(sec, {})[mid] = usable[mid]
    return out


# ---------------------------------------------------------------------------------------------------------------
# The browser's twin: formatting, keyed elements, the language picker and the suggestion
# ---------------------------------------------------------------------------------------------------------------

# Runs in the shell's script (site-*.js) on every page. I18N_CONF is written by the build: the languages, their
# names, each catalogue's address and the pages that have an address in every language.
SHELL_JS = r"""
(function(){
const C = I18N_CONF, H = document.documentElement, K = 'setuhq-lang', st = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
const P = C.locales.includes(H.lang) ? H.lang : 'en', auto = document.body && (document.body.hasAttribute('data-i18n-auto') || document.body.hasAttribute('data-chrome')), S = st(K);
const lang = P !== 'en' ? P : (auto && C.locales.includes(S) ? S : 'en');
const esc = s => String(s).replace(/[&<>"]/g, c => '&#' + c.charCodeAt(0) + ';');
function fmt(m, a, L){
  a = a || {}; let i = 0;
  const num = (v, s) => { const o = {}; if (s === 'integer') o.maximumFractionDigits = 0; else if (s === 'percent' || s === '::percent') o.style = 'percent';
    else { const d = /^::\s*\.(0*)$/.exec(s || ''); if (d) o.minimumFractionDigits = o.maximumFractionDigits = d[1].length; else o.maximumFractionDigits = 3; }
    return L === 'en' && o.style !== 'percent' ? new Intl.NumberFormat('en-US', o).format(v) : new Intl.NumberFormat(L, o).format(v); };
  const date = v => { const d = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v)); if (!d) return esc(v); if (L === 'en') return d[0];
    return new Intl.DateTimeFormat(L, {year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC'}).format(new Date(Date.UTC(+d[1], d[2] - 1, +d[3]))); };
  function text(pl, n){
    let o = '';
    while (i < m.length){
      const c = m[i], d = m[i + 1];
      if (c === "'"){ if (d === "'"){ o += c; i += 2; continue; }
        if ('{}|'.includes(d) || (pl && d === '#')){ const j = m.indexOf("'", i + 1); o += m.slice(i + 1, j); i = j + 1; continue; } }
      if (c === '}') return o;
      if (c === '#' && pl){ o += num(n); i++; continue; }
      if (c === '{'){ i++; o += arg(); continue; }
      o += c; i++;
    }
    return o;
  }
  function arg(){
    const h = /^\s*(\w+)\s*(?:,\s*(\w+)\s*,?)?/.exec(m.slice(i)); i += h[0].length;
    const v = a[h[1]], ty = h[2];
    if (!ty){ i = m.indexOf('}', i) + 1; return v === undefined ? '{' + h[1] + '}' : esc(v); }
    if (ty === 'number' || ty === 'date'){ const j = m.indexOf('}', i), s = m.slice(i, j).trim(); i = j + 1; return ty === 'date' ? date(v) : num(v, s); }
    const of = /^\s*offset:\s*(\d+)/.exec(m.slice(i)); let off = 0; if (of){ off = +of[1]; i += of[0].length; }
    const n = +v - off, cat = ty === 'plural' ? new Intl.PluralRules(L).select(n) : String(v); let ex = null, hit = null, oth = '';
    for (;;){ const b = /^\s*(=?[\w-]+)\s*\{/.exec(m.slice(i)); if (!b) break; i += b[0].length; const body = text(ty === 'plural', n); i++;
      if (b[1] === '=' + v) ex = body; else if (b[1] === cat) hit = body; if (b[1] === 'other') oth = body; }
    i = m.indexOf('}', i) + 1;
    return ex !== null ? ex : hit !== null ? hit : oth;
  }
  return text(false);
}
const SI = window.SetuI18n = {lang, page: P, cat: null, conf: C,
  T: (id, en, a) => { const m = (SI.cat && SI.cat[id]) || en || id; return lang === 'en' && !a && m.indexOf('{') < 0 ? m : fmt(m, a, lang); },
  fmt: (m, a, L) => fmt(m, a, L || lang),
  href: h => { if (lang === 'en' || !h || h[0] !== '/' || h[1] === '/') return h; const u = h.split(/(?=[?#])/), p = u.shift(); return C.main.includes(p) ? '/' + lang + p + u.join('') : h; },
  apply(root){
    if (!SI.cat || !root) return;
    const els = [...(root.querySelectorAll ? root.querySelectorAll('[data-i18n],[data-i18n-attr],a[href^="/"]') : [])];
    if (root.matches && root.matches('[data-i18n],[data-i18n-attr]')) els.push(root);
    for (const el of els){
      let a; try { a = JSON.parse(el.dataset.i18nArgs || '{}'); } catch (e) { a = {}; }
      for (const k in a) if (k.endsWith('@') && SI.cat[a[k]]) a[k.slice(0, -1)] = fmt(SI.cat[a[k]], {}, lang);
      const id = el.dataset.i18n; if (id && SI.cat[id]){ el.innerHTML = fmt(SI.cat[id], a, lang); for (const x of el.querySelectorAll('a[href^="/"]')) x.setAttribute('href', SI.href(x.getAttribute('href'))); }
      for (const s of (el.dataset.i18nAttr || '').split('|').filter(Boolean)){ const [n, k] = s.split(':'); if (SI.cat[k]) el.setAttribute(n, fmt(SI.cat[k], a, lang).replace(/&#(\d+);/g, (x, d) => String.fromCharCode(d))); }
      if (el.tagName === 'A'){ const h = el.getAttribute('href'), n = SI.href(h); if (n !== h) el.setAttribute('href', n); }
    }
    marks(root);
    if (SI.auto) SI.auto(root);
  }};
// The picker says which language the page is in (a small page's header arrives after the catalogue).
function marks(root){
  if (!root.querySelectorAll) return;
  for (const n of root.querySelectorAll('.mtnote')) n.hidden = false;
  for (const n of root.querySelectorAll('.langcode')) n.textContent = lang === 'zh-Hans' ? 'ZH' : lang.toUpperCase();
  for (const a of root.querySelectorAll('.langmenu a[data-lang]')) if (a.dataset.lang === lang) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
}
const load = L => fetch(C.cat[L]).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
SI.ready = lang === 'en' ? Promise.resolve() : load(lang).then(c => { SI.cat = c; H.lang = lang; SI.apply(document);
  if (C.auto){ const x = document.createElement('script'); x.src = C.auto; document.head.appendChild(x); }
}).catch(e => console.warn('SetuHQ: the translation could not load', e));
// The picker remembers the choice; on a page with one address the choice applies in place, on reload.
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-lang]'); if (!a) return;
  st(K, a.dataset.lang); st(K + '-hint', '1');
  if (a.getAttribute('href') === location.pathname || auto){ e.preventDefault(); location.reload(); }
});
// A suggestion, never a redirect: the stored choice, or on a first visit the browser's language, when this page is in another.
const alt = l => { const x = document.querySelector('link[rel=alternate][hreflang="' + l + '"]'); return x ? new URL(x.href).pathname : null; };
let want = C.locales.includes(S) ? S : null;
if (!want && !st(K + '-hint')) for (const l of navigator.languages || []){ const b = l.toLowerCase(), c = b.startsWith('zh') ? (/hant|tw|hk|mo/.test(b) ? null : 'zh-Hans') : /^n[on]\b/.test(b) ? 'nb' : b.split('-')[0]; if (C.locales.includes(c)){ want = c; break; } }
if (want && want !== lang && (alt(want) || auto)){
  const go = alt(want) || location.pathname;
  (want === 'en' ? Promise.resolve({}) : load(want)).then(c => {
    const f = (id, en) => fmt(c[id] || en, {}, want), b = document.createElement('div');
    b.className = 'langhint'; b.lang = want; b.setAttribute('role', 'region'); b.setAttribute('aria-label', f('i18n.suggest.label', 'Language'));
    b.innerHTML = `<p>${f('i18n.suggest.text', 'This page is also in English.')} <a href="${esc(go)}" data-lang="${esc(want)}">${f('i18n.suggest.go', 'Read it in English')}</a></p><button type="button" class="btn" aria-label="${f('i18n.suggest.dismiss', 'Dismiss')}">×</button>`;
    b.querySelector('button').onclick = () => { st(K + '-hint', '1'); if (!S) st(K, lang); b.remove(); };
    document.body.prepend(b);
  }).catch(() => {});
}
})();
"""


# The page text the scripts draw (assets/i18n-auto-*.js, loaded with a catalogue in another language): blocks with no
# key of their own, by the hash of their template, numbers and the page's names as arguments (docs/TRANSLATING.md).
AUTO_JS = r"""
(function(){
const SI = window.SetuI18n; if (!SI) return;
// What the page's scripts draw, by its text (the twin of setuhq.i18n_auto): each block of text and inline markup with
// no key of its own and words of its own (a row of spans is its spans) is a message whose id is a hash of its template, numbers and the page's names as arguments.
const BL = /^(P|LI|H[1-6]|FIGCAPTION|TD|TH|DT|DD|SUMMARY|CAPTION|LABEL|BUTTON|LEGEND|BLOCKQUOTE|A|DIV|SPAN|B|STRONG|EM|SMALL|HEADER|FOOTER|SECTION|ASIDE|FIGURE|OPTION|TEXT|TSPAN)$/,
  IL = /^(A|B|STRONG|I|EM|CODE|SPAN|SUB|SUP|ABBR|SMALL|BR|WBR|KBD|MARK|TIME|Q|CITE|S|U|VAR|BDI|DATA)$/i,
  SKX = 'script,style,svg,template,pre,canvas,noscript,textarea,select,[data-i18n],[translate=no],.langpick,.langhint',
  NUM = /(?<![\w.\-−])[-−+]?\d+(?:[.,:]\d+)*(?!\w)|(?<=[-–−])\d+(?:[.,]\d+)*(?!\w)/g, ATS = ['aria-label', 'alt', 'title', 'placeholder'],
  DONE = new WeakMap();
const h53 = s => { let a = 0xdeadbeef, b = 0x41c6ce57; for (let i = 0; i < s.length; i++){ const c = s.charCodeAt(i); a = Math.imul(a ^ c, 2654435761); b = Math.imul(b ^ c, 1597334677); }
  a = Math.imul(a ^ (a >>> 16), 2246822507) ^ Math.imul(b ^ (b >>> 13), 3266489909); b = Math.imul(b ^ (b >>> 16), 2246822507) ^ Math.imul(a ^ (a >>> 13), 3266489909);
  return 'js.' + (4294967296 * (2097151 & b) + (a >>> 0)).toString(36); };
const prose = t => { t = t.replace(/<[^>]*>|\{\w+\}/g, ' '); return /(^|[^\w-])[a-z][a-z']{2,}\b/.test(t) || (/\b[A-Z][a-z]{2,}\b/.test(t) && !/\d/.test(t) && t.trim().split(/\s+/).length <= 4); };
const q = s => s.replace(/'([{}])/g, "''$1").replace(/[{}]/g, "'$&'");
function tpl(html, names){
  const a = {}; let k = 0, j = 0;
  const t = html.split(/(<[^>]*>)/).map(p => {
    if (p[0] === '<') return q(p);
    let o = '', pos = 0;
    const parts = [];
    for (const n of names){ let i; while ((i = p.indexOf(n, pos)) >= 0 && n){ parts.push([i, n]); pos = i + n.length; } pos = 0; }
    parts.sort((x, y) => x[0] - y[0]);
    let last = 0;
    const num = s => s.replace(NUM, m => { const key = 'n' + k++; a[key] = m; return '\u0001' + key + '\u0002'; });
    for (const [i, n] of parts){ if (i < last) continue; o += num(p.slice(last, i)); const key = 's' + j++; a[key] = n; o += '\u0001' + key + '\u0002'; last = i + n.length; }
    o += num(p.slice(last));
    return q(o).replace(/\u0001(\w+)\u0002/g, '{$1}');
  }).join('').replace(/\s+/g, ' ').trim();
  return [t, a];
}
// A translated template with its arguments: numbers in the reader's format (not years, versions or catalogue codes).
function fill(m, a){
  m = m.replace(/''/g, '\u0003').replace(/'([{}])'/g, '$1').replace(/\u0003/g, "'");
  return m.replace(/\{(\w+)\}/g, (x, key, at) => { const v = a[key]; if (v === undefined) return x;
    if (key[0] !== 'n' || SI.lang === 'en' || /(\bBY|[A-Za-z]-|\bv|Python|DR)\s?$/.test(m.slice(0, at))) return v;
    const d = /^[-−]?\d{1,3}(,\d{3})+(\.\d+)?$|^[-−]?\d+\.\d+$/.exec(v); if (!d) return v;
    const f = (v.split('.')[1] || '').length; return new Intl.NumberFormat(SI.lang, {minimumFractionDigits: f, maximumFractionDigits: f}).format(+v.replace(/[,−]/g, x => x === '−' ? '-' : '')); });
}
function auto(root){
  if (SI.lang === 'en' || !SI.cat || !root || !root.querySelectorAll) return;
  // The page's names (a planet or star page's heading, its links to planets and stars), not on a main page, whose
  // headings are in the reader's language: the same text gives the same template in every language.
  const p = location.pathname.replace(/^\/[^/]+(?=\/)/, x => SI.conf.locales.includes(x.slice(1)) ? '' : x);
  const names = SI.conf.main.includes(p) ? [] : [...new Set([...document.querySelectorAll('h1, a[href^="/planets/"], a[href^="/stars/"]')].map(e => e.textContent.trim()).filter(n => n.length > 2 && n.length < 60))].sort((x, y) => y.length - x.length);
  const walk = el => {
    for (const c of el.children){
      if (c.matches(SKX)) continue;
      for (const at of ATS){ const v = c.getAttribute(at); if (v && DONE.get(c) !== at + v && prose(v)){ const [t, a] = tpl(v.replace(/&/g, '&amp;').replace(/</g, '&lt;'), names), m = SI.cat[SI.hash(t, v)]; if (m){ const n = fill(m, a).replace(/<[^>]*>/g, '').replace(/&lt;/g, '<').replace(/&amp;/g, '&'); c.setAttribute(at, n); DONE.set(c, at + n); } } }
      if (BL.test(c.tagName.toUpperCase()) && [...c.childNodes].some(n => n.nodeType === 3 && /[A-Za-z]{2}/.test(n.data)) && [...c.children].every(function ok(x){ return IL.test(x.tagName) && !x.matches('[data-i18n]') && [...x.children].every(ok); })){
        const h = c.innerHTML; if (DONE.get(c) === h) continue;
        const [t, a] = tpl(h, names);
        if (prose(t)){ const m = SI.cat[SI.hash(t, h)]; if (m){ c.innerHTML = fill(m, a); DONE.set(c, c.innerHTML); } continue; }
      }
      walk(c);
    }
  };
  walk(root.body || root);
}
let pend = null;
new MutationObserver(ms => { if (SI.lang === 'en' || !SI.cat) return; for (const x of ms){ const e = x.target.nodeType === 1 ? x.target : x.target.parentElement, t = e && (e.parentElement || e); if (t) (pend = pend || new Set()).add(t); }
  if (pend && !pend.t){ pend.t = setTimeout(() => { const s = pend; pend = null; for (const t of s) if (t.isConnected) auto(t); }, 60); } }).observe(document.documentElement, {childList: true, subtree: true, characterData: true});
Object.assign(SI, {auto, tpl, prose, h53, fill, hash: h53});
// This part of the site's drawn text (setuhq.i18n.js_catalogues), then the page.
const seg = location.pathname.split('/').filter(Boolean); if (SI.conf.locales.includes(seg[0])) seg.shift();
fetch('/assets/i18n/js-JS_VERSION/' + SI.lang + '/' + (seg[0] || 'home') + '.json').then(r => r.ok ? r.json() : {}).catch(() => ({}))
  .then(c => { if (SI.cat) Object.assign(SI.cat, c); auto(document); });
})();
"""

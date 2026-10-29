# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Page prose as messages, without a key in the English markup (docs/TRANSLATING.md, "Page text").

The site's long-form text (the Methods chapters, the evidence write-ups, the docs) is written once, in English, in
the code that builds each page. Rather than give every sentence an id by hand, each block of text on a main page
(a paragraph, a list item, a heading, a caption, a table cell: an element whose content is text and inline markup
only, inside <main>, with no key of its own) is a message whose id is the hash of its template:

* numbers in the text become arguments ({n0}, {n1}, ...), so a count that changes keeps the message and its
  translations, and the language formats nothing it should not;
* inline markup (links, <b>, <code>) stays in the message, attributes and all, and every translation must keep it.

``tools/i18n.py extract`` collects these templates from the committed English site (site/) into en.arb with the
prefix ``pg.``; ``localize`` puts each language's translation in place when the /<lang>/ pages are written. A block
whose translation is missing or stale stays English. The English pages are never changed.
"""

from __future__ import annotations

import hashlib
import html as _html
import re

PREFIX = "pg."
# Elements whose content can be one message (when it is text and inline markup only).
BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "td", "th", "dt", "dd", "summary", "caption", "label",
         "button", "legend", "blockquote", "a", "div", "span", "b", "strong", "em", "small", "header", "footer", "section",
         "aside", "figure", "option", "text", "tspan"}
INLINE = {"a", "b", "strong", "i", "em", "code", "span", "sub", "sup", "abbr", "small", "br", "wbr", "kbd", "mark",
          "time", "q", "cite", "s", "u", "var", "bdi", "data"}
SKIP = {"script", "style", "svg", "template", "pre", "canvas", "noscript", "textarea", "select", "math"}
ATTRS = ("aria-label", "alt", "title", "placeholder")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

_TOK = re.compile(r"<!--.*?-->|<(/?)([a-zA-Z][\w-]*)((?:\s+[^\s=>/]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?)*)\s*(/?)>|[^<]+|<",
                  re.S)
_NUM = re.compile(r"(?<![\w.\-−])[-−+]?\d+(?:[.,:]\d+)*(?![\w])|(?<=[\-–−])\d+(?:[.,]\d+)*(?![\w])")
_WORDS = re.compile(r"(?<![\w-])[a-z][a-z']{2,}\b")


class _Node:
    __slots__ = ("tag", "attrs", "start", "inner", "end", "children", "keyed", "text")

    def __init__(self, tag, attrs, start, inner):
        self.tag, self.attrs, self.start, self.inner, self.end = tag, attrs, start, inner, -1
        self.children, self.text = [], False
        self.keyed = "data-i18n=" in attrs or "data-i18n-auto" in attrs or 'translate="no"' in attrs


def _tree(src: str, lo: int, hi: int) -> _Node:
    root = _Node("#root", "", lo, lo)
    stack = [root]
    skip_until = None
    for m in _TOK.finditer(src, lo, hi):
        if skip_until:
            if m.group(2) and m.group(1) == "/" and m.group(2).lower() == skip_until:
                skip_until = None
                node = stack.pop()
                node.end = m.end()
            continue
        if m.group(2) is None:
            if not m.group(0).startswith("<!--") and m.group(0).strip():
                stack[-1].text = True
            continue
        close, tag, attrs, selfclose = m.group(1), m.group(2).lower(), m.group(3) or "", m.group(4)
        if close:
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == tag:
                    for node in stack[i:]:
                        node.end = m.start() if node is not stack[i] else m.end()
                    del stack[i:]
                    break
            continue
        node = _Node(tag, attrs, m.start(), m.end())
        stack[-1].children.append(node)
        if tag in VOID or selfclose:
            node.end = m.end()
            continue
        stack.append(node)
        if tag in SKIP:
            skip_until = tag
    for node in stack[1:]:
        node.end = hi
    return root


def _inline_only(node: _Node) -> bool:
    return all(c.tag in INLINE and not c.keyed and _inline_only(c) for c in node.children)


def _inner_end(src: str, node: _Node) -> int:
    i = src.rfind("</", node.inner, node.end)
    return i if i >= node.inner else node.end


def _quote(text: str) -> str:
    """Literal text as ICU MessageFormat (DOUBLE_OPTIONAL apostrophes): braces quoted, an apostrophe before a brace doubled."""
    text = text.replace("'{", "''{").replace("'}", "''}")
    return re.sub(r"([{}])", r"'\1'", text)


def template(inner: str) -> tuple[str, dict]:
    """The message for a block's inner HTML: its numbers as {n0}, {n1}, ... (in text only, never in markup), ICU-quoted."""
    args: dict[str, str] = {}
    out = []
    for m in re.finditer(r"<[^>]*>|[^<]+", inner):
        piece = m.group(0)
        if piece.startswith("<"):
            out.append(_quote(piece))
            continue
        pos, parts = 0, []
        for n in _NUM.finditer(piece):
            parts.append(_quote(piece[pos:n.start()]))
            key = f"n{len(args)}"
            args[key] = n.group(0)
            parts.append("{" + key + "}")
            pos = n.end()
        parts.append(_quote(piece[pos:]))
        out.append("".join(parts))
    return re.sub(r"\s+", " ", "".join(out)).strip(), args


def message_id(tpl: str) -> str:
    return PREFIX + hashlib.sha256(tpl.encode("utf-8")).hexdigest()[:10]


def _prose(text: str) -> bool:
    """Text a reader reads as words: a lowercase word, or a short label of words with no digits ("Speed")."""
    plain = _html.unescape(re.sub(r"<[^>]+>", " ", text))
    if _WORDS.search(plain):
        return True
    return bool(re.search(r"\b[A-Z][a-z]{2,}\b", plain)) and not re.search(r"\d", plain) and len(plain.split()) <= 4


def _region(src: str) -> tuple[int, int]:
    a = src.find("<main")
    b = src.rfind("</main>")
    return (a, b) if a >= 0 and b > a else (0, 0)


def blocks(src: str):
    """Every unkeyed text block and translatable attribute inside <main>: (kind, start, end, template, args), where
    [start, end) is the inner HTML (kind "html") or the attribute's value (kind "attr")."""
    lo, hi = _region(src)
    if hi <= lo:
        return []
    found = []

    def walk(node: _Node, inside_key: bool):
        for c in node.children:
            keyed = inside_key or c.keyed
            for an in ATTRS:
                if keyed and f"data-i18n-attr=" in c.attrs and an + ":" in c.attrs:
                    continue
                m = re.search(r'(?:^|\s)' + an + r'="([^"]*)"', c.attrs)
                if m and _prose(m.group(1)) and f"{an}:" not in (re.search(r'data-i18n-attr="([^"]*)"', c.attrs) or [None, ""])[1]:
                    vs = c.start + 1 + len(c.tag) + m.start(1)
                    tpl, args = template(m.group(1))
                    found.append(("attr", vs, vs + len(m.group(1)), tpl, args))
            if c.tag in SKIP or keyed:
                if not keyed:
                    continue
                walk(c, True)
                continue
            if c.tag in BLOCK and c.end > c.inner and (c.text or c.children) and _inline_only(c):
                e = _inner_end(src, c)
                inner = src[c.inner:e]
                if _prose(inner) and not re.fullmatch(r"\s*<code>.*</code>\s*", inner, re.S):
                    tpl, args = template(inner)
                    found.append(("html", c.inner, e, tpl, args))
                    continue
            walk(c, False)
    walk(_tree(src, lo, hi), False)
    return found


_GROUPED = re.compile(r"^[-−]?\d{1,3}(,\d{3})+(\.\d+)?$|^[-−]?\d+\.\d+$")
_NOT_A_NUMBER = re.compile(r"(\bBY|[A-Za-z]-|\bv|Python|DR)\s?$")


def local_numbers(tpl: str, args: dict, lang: str) -> dict:
    """``args`` with each number in the reader's format (1,234.5 -> 1.234,5 in German), as the browser's twin does:
    not a whole number without a group separator (a year, a count, a sector), and not a version or a licence."""
    if lang == "en":
        return args
    from setuhq.i18n import format_number

    out = dict(args)
    for key, v in args.items():
        at = tpl.find("{" + key + "}")
        if not key.startswith("n") or at < 0 or not _GROUPED.match(v) or _NOT_A_NUMBER.search(tpl[:at]):
            continue
        dec = len(v.split(".")[1]) if "." in v else 0
        out[key] = format_number(float(v.replace(",", "").replace("−", "-")), lang, dec)
    return out


def localize(src: str, lang: str, catalogue: dict[str, str], *, link=None) -> str:
    """``src`` (an English page) with every block and attribute that has a usable translation in ``catalogue``."""
    from setuhq.i18n import format_message

    out, pos = [], 0
    for kind, s, e, tpl, args in sorted(blocks(src), key=lambda b: b[1]):
        if s < pos:
            continue
        msg = catalogue.get(message_id(tpl))
        if not msg:
            continue
        try:
            text = format_message(msg, local_numbers(tpl, args, lang), lang)
        except Exception:  # a malformed translation: the English stays
            continue
        if kind == "attr":
            text = _html.escape(_html.unescape(re.sub(r"<[^>]+>", "", text)), quote=True)
        elif link:
            text = re.sub(r'href="([^"]*)"', lambda h: f'href="{link(h.group(1))}"', text)
        out.append(src[pos:s])
        out.append(text)
        pos = e
    out.append(src[pos:])
    return "".join(out)


def harvest(pages: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    """{message id: (template, [page paths])} for every block on the given English pages ({path: html})."""
    found: dict[str, tuple[str, list[str]]] = {}
    for path, src in sorted(pages.items()):
        for _kind, _s, _e, tpl, _args in blocks(src):
            mid = message_id(tpl)
            if mid in found:
                if path not in found[mid][1]:
                    found[mid][1].append(path)
            else:
                found[mid] = (tpl, [path])
    return found

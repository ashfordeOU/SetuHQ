# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Comments out of the built script and stylesheet (the site's budgets, docs/SITE.md).

The source keeps its comments; the files the site serves (app-*.js, site-*.js, site-*.css) drop them, with the
indentation and blank lines they leave. Nothing else changes: no renaming, no reordering. Strings, template
literals (and the code inside their ``${...}``) and regular-expression literals are read as such, so a ``//`` or
``/*`` inside one stays. A block comment that spanned lines leaves a line break, so no statement runs into the next.
"""

from __future__ import annotations

import re

# After one of these (or at the start), a slash begins a regular expression, not a division.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^") | {""}
_REGEX_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "instanceof", "yield", "await"}


def strip_js(src: str) -> str:
    """``src`` without comments, leading indentation or blank lines outside strings and template literals."""
    out: list[str] = []
    i, n = 0, len(src)
    stack: list[str] = []  # 'tpl' while inside a template literal's text; '{' for a brace inside ${ } code
    last = ""  # the last significant character (or word) of code, for telling a regex from a division
    at_line_start = True

    def emit(s: str):
        nonlocal at_line_start
        out.append(s)
        if s:
            at_line_start = s.endswith("\n")

    while i < n:
        c = src[i]
        if stack and stack[-1] == "tpl":
            # inside a template literal's text: copy until ` or ${
            if c == "\\":
                emit(src[i:i + 2])
                i += 2
                continue
            if c == "`":
                stack.pop()
                emit(c)
                last = "`"
                i += 1
                continue
            if c == "$" and src.startswith("${", i):
                stack.append("{")
                emit("${")
                last = "{"
                i += 2
                continue
            emit(c)
            i += 1
            continue
        if c in " \t" and at_line_start:
            i += 1
            continue
        if c == "\n":
            if not at_line_start:
                emit("\n")
            i += 1
            continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            if "\n" in src[i:j] and not at_line_start:
                emit("\n")
            elif not at_line_start and out and not out[-1].endswith((" ", "\n")):
                emit(" ")
            i = j
            continue
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            emit(src[i:j + 1])
            last = c
            i = j + 1
            continue
        if c == "`":
            stack.append("tpl")
            emit(c)
            i += 1
            continue
        if c == "/" and (last in _REGEX_AFTER or last in _REGEX_WORDS):
            j, cls = i + 1, False
            while j < n:
                d = src[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "[":
                    cls = True
                elif d == "]":
                    cls = False
                elif d == "/" and not cls:
                    break
                elif d == "\n":
                    break
                j += 1
            m = re.match(r"[a-z]*", src[j + 1:])
            end = j + 1 + (m.end() if m else 0)
            emit(src[i:end])
            last = "/"
            i = end
            continue
        if c == "{" and stack:
            stack.append("{")
        elif c == "}" and stack and stack[-1] == "{":
            stack.pop()
            if stack and stack[-1] == "tpl":
                emit(c)
                i += 1
                continue
        if c.isalnum() or c in "_$":
            m = re.match(r"[\w$]+", src[i:])
            word = m.group(0)
            emit(word)
            last = word if word in _REGEX_WORDS else "a"
            i += len(word)
            continue
        emit(c)
        if not c.isspace():
            last = c
        i += 1
    text = "".join(out)
    return re.sub(r"[ \t]+\n", "\n", text)


def strip_css(src: str) -> str:
    """``src`` without comments, indentation or blank lines (strings are kept as they are)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    lines = (l.strip() for l in "".join(out).split("\n"))
    return "\n".join(l for l in lines if l) + "\n"

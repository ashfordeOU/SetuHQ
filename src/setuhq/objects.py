# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""One object model: every planet and star has one canonical page, #/planet/<slug> or #/star/<slug>.

The page's objSlug (app.py) applies the same rule, and the tests check that every name in the catalogue
gives its stored slug either way, so any view can link a name without loading the catalogue.
"""

from __future__ import annotations

import html
import re


def slugify(name: str) -> str:
    """The URL slug of a planet or star name (the same rule as scripts/fetch_exoplanet_catalogue.py)."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "x"


def planet_href(name: str) -> str:
    return "#/planet/" + slugify(name)


def star_href(name: str) -> str:
    return "#/star/" + slugify(name)


def obj_link(kind: str, name: str, label: str | None = None, cls: str = "") -> str:
    """The one renderer (Python side) for a link to a planet or star page; objLink is the page's twin."""
    e = html.escape
    href = star_href(name) if kind == "star" else planet_href(name)
    label = label if label is not None else name
    # A generic label ("Planet page ›") gets the object's name in its accessible name.
    aria = f' aria-label="{e(name)}, {kind} page"' if name not in label else ""
    return f'<a class="objlink{" " + cls if cls else ""}" data-{kind}="{e(name)}" href="{href}"{aria}>{e(label)}</a>'

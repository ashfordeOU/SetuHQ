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
    return f'<a class="objlink{" " + cls if cls else ""}" data-{kind}="{e(name)}" href="{href}">{e(label if label is not None else name)}</a>'

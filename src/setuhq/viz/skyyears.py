# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V04 sky by year: every catalogue host (RA, Dec, method, year) on a Mollweide map, filling in by discovery year.

Used on: /explore/, Home (compact), Methods population. Owner: P2 (docs/SITE.md, "The visual system"). Until P2 builds it this module keeps its
final signature and draws nothing: :func:`html` returns "" and the caller leaves its band out.
"""

from __future__ import annotations

from setuhq.viz import require_source

CSS = ""
JS = ""


def html(data: dict, **opts) -> str:
    """The component's server-rendered markup (with its no-JS fallback and text alternative). Every component that
    draws data prints its source: ``data["source"]`` is required."""
    require_source(data)
    return ""

def data(app_data: dict) -> dict:
    """This component's section of the build-time data file (sky.json): {} until P2 builds it."""
    return {}

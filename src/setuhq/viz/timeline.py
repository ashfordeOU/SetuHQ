# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V12 timeline: discoveries per year by method, from the catalogue.

Used on: /explore/, Home, Methods population and history. Owner: P2 (docs/SITE.md, "The visual system"). Until P2 builds it this module keeps its
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
    """This component's section of the build-time data file (stories.json): {} until P2 builds it."""
    return {}

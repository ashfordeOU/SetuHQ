# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V09 temperature strip: teff_rgb from 2,500 to 10,000 K with the showcase stars' TIC Teff and the Sun marked; a two-handle filter mode.

Used on: Home, catalogue filter, Methods equations. Owner: P1 (docs/SITE.md, "The visual system"). Until P1 builds it this module keeps its
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

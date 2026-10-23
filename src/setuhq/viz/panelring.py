# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V06 panel ring: a dip's stored marks and calibrated weights converging on its stored panel score.

Used on: dip pages, Home (lead dip), Evidence (panel mode). Owner: P3 (docs/SITE.md, "The visual system"). Until P3 builds it this module keeps its
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

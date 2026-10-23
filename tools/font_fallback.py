# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The metric-matched fallback faces for Geist and Geist Mono (no layout shift when the web font arrives).

A local system font (Arial for Geist, Menlo for Geist Mono) is scaled so its average character width matches the
web font's, and its ascent and descent are overridden to the web font's. Both widths use the same rule, the
classic OS/2 xAvgCharWidth weighting (lower-case a–z and the space, weighted by English letter frequency, as in the
OpenType OS/2 table, versions 0–2), so they compare like with like:

* Geist and Geist Mono: read from tools/readme-fonts/*.ttf (the default instance of the variable files).
* Arial: unitsPerEm 2048, ascent 1854, descent 434, xAvgCharWidth 904 (its OS/2 table; the same values as
  @capsizecss/metrics' "arial").
* Menlo: unitsPerEm 2048, ascent 1901, descent 483, every glyph 1233 wide (a monospace; @capsizecss/metrics' "menlo").

    python tools/font_fallback.py          # print the values; design.FONT_FALLBACK must equal them (a test checks)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "readme-fonts"
# OS/2 v0–2 xAvgCharWidth weights (per 1000), a–z then the space.
WEIGHTS = dict(zip("abcdefghijklmnopqrstuvwxyz ", (64, 14, 27, 35, 100, 20, 14, 42, 63, 3, 6, 35, 20, 56, 56, 17, 4, 49, 56, 71,
                                                  31, 10, 18, 3, 18, 2, 166)))
SYSTEM = {"Arial": {"upm": 2048, "ascent": 1854, "descent": 434, "avg": 904},
          "Menlo": {"upm": 2048, "ascent": 1901, "descent": 483, "avg": 1233}}
FACES = [("Geist Fallback", "Geist-latin-wght.ttf", "Arial", ('local("Arial")', 'local("Helvetica Neue")', 'local("Helvetica")')),
         ("Geist Mono Fallback", "GeistMono-latin-wght.ttf", "Menlo", ('local("Menlo")', 'local("Consolas")', 'local("DejaVu Sans Mono")'))]


def web_metrics(path: Path) -> dict:
    from fontTools.ttLib import TTFont

    f = TTFont(str(path))
    cmap, hmtx = f.getBestCmap(), f["hmtx"]
    avg = sum(w * hmtx[cmap[ord(ch)]][0] for ch, w in WEIGHTS.items()) / 1000
    return {"upm": f["head"].unitsPerEm, "ascent": f["hhea"].ascent, "descent": -f["hhea"].descent, "avg": avg}


def fallback_values(fonts: Path = FONTS) -> dict:
    """{face: {"src": [...], "size_adjust": %, "ascent_override": %, "descent_override": %}}, rounded to 0.01%."""
    out = {}
    for face, file, system, src in FACES:
        w, s = web_metrics(fonts / file), SYSTEM[system]
        size = (w["avg"] / w["upm"]) / (s["avg"] / s["upm"])
        out[face] = {"src": list(src), "size_adjust": round(size * 100, 2),
                     "ascent_override": round(w["ascent"] / w["upm"] / size * 100, 2),
                     "descent_override": round(w["descent"] / w["upm"] / size * 100, 2)}
    return out


if __name__ == "__main__":
    json.dump(fallback_values(), sys.stdout, indent=1, ensure_ascii=False)
    print()

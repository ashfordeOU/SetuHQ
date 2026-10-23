# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The site's three astronomical symbols as a tiny font: ⊕ (Earth), ☉ (Sun) and ★ (star).

Geist and Geist Mono have no glyph for them, so in "1.87 R⊕" the browser falls back to a system font whose ⊕ is about
twice as wide as a letter. fonts/fonts.css registers this file under both families for exactly these three code
points (unicode-range), so every page, canvas label and stand-alone page gets symbols the width of a Geist Mono
character (600 of 1,000 units), centred on the cap height. The outlines are drawn here (circles, a plus, a dot, a
five-pointed star); no third-party glyph is used.

    python tools/symbol_font.py           # write src/setuhq/fonts/files/setu-symbols.woff
    python tools/symbol_font.py --check   # fail when the committed file differs from what this writes
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "setuhq" / "fonts" / "files" / "setu-symbols.woff"
UPM, ADV, ASC, DESC = 1000, 600, 1005, 295
CY = 355            # half of Geist's cap height (710)
R_OUT, STROKE = 285, 62


def _circle(cx, cy, r, n=64, clockwise=True):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    return pts[::-1] if clockwise else pts


def _rect(x0, y0, x1, y1):  # clockwise in font coordinates (y up)
    return [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]


def _star(cx, cy, r_out, r_in):
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = math.pi / 2 - i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts  # clockwise (angle decreasing)


def glyphs() -> dict[str, list[list[tuple[float, float]]]]:
    cx = ADV / 2
    ring = [_circle(cx, CY, R_OUT), _circle(cx, CY, R_OUT - STROKE, clockwise=False)]
    inner = R_OUT - STROKE + 4
    h = STROKE / 2
    plus = [_rect(cx - inner, CY - h, cx + inner, CY + h), _rect(cx - h, CY - inner, cx + h, CY + inner)]
    return {"earth": ring + plus, "sun": ring + [_circle(cx, CY, 62)], "star": [_star(cx, CY + 10, 300, 120)]}


def build() -> bytes:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    names = [".notdef", "space", "earth", "sun", "star"]
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({0x20: "space", 0x2295: "earth", 0x2609: "sun", 0x2605: "star"})
    shapes = glyphs()
    out = {}
    for n in names:
        pen = TTGlyphPen(None)
        for contour in shapes.get(n, []):
            pen.moveTo(tuple(round(v) for v in contour[0]))
            for p in contour[1:]:
                pen.lineTo(tuple(round(v) for v in p))
            pen.closePath()
        out[n] = pen.glyph()
    fb.setupGlyf(out)
    fb.setupHorizontalMetrics({n: (ADV if n != ".notdef" else 500, 0) for n in names})
    fb.setupHorizontalHeader(ascent=ASC, descent=-DESC)
    fb.setupNameTable({"familyName": "Setu Symbols", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=ASC, sTypoDescender=-DESC, usWinAscent=ASC, usWinDescent=DESC, xAvgCharWidth=ADV)
    fb.setupPost()
    fb.font["head"].created = fb.font["head"].modified = 0  # reproducible bytes
    fb.font.flavor = "woff"
    buf = io.BytesIO()
    fb.font.save(buf, reorderTables=True)
    return buf.getvalue()


if __name__ == "__main__":
    data = build()
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_bytes() == data
        print("symbol_font --check: " + ("current" if ok else f"{OUT} is stale (run python tools/symbol_font.py)"))
        sys.exit(0 if ok else 1)
    OUT.write_bytes(data)
    print(f"symbol_font: {len(data):,} bytes, {OUT}")

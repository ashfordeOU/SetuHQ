#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Generate the README's figures from committed data, in a light and a dark variant.

Every picture under docs/assets/readme/ (except the app screenshots in app/) and every file in
docs/assets/brand/ (except its README) is written by this
script as a self-contained SVG in the visual system of the SetuHQ app: the app's colour tokens
(Apple dark and light; known #0A84FF, open #FFD60A, rejected #FF453A, Sentinels #64D2FF, Probes
#BF5AF2 in the dark theme), its typeface (Geist and Geist Mono) and one figure grid:

    1200 x 600 px, 40 px margins, a mono eyebrow, a 24 px title, the plot between y = 108 and
    y = 532, and a footer that names the source file and the commit that last changed it.

What each figure is drawn from (nothing is invented; numbers are read, or computed by the
package's own functions, at generation time):

* docs/assets/brand/ (the logo lockup, the wordmark, app icons, the favicon and the social card):
  the Setu mark (docs/assets/readme/brand/setu-mark.svg, the Setu brand kit's file) cropped to its own
  box, "Setu" in Unbounded 600 and "HQ" with the transit Q (see docs/assets/brand/README.md);
* hero: every planet in docs/results/exoplanet_map.json (exoplanet.eu), placed by galactic longitude
  (setuhq.galaxy.galactic_lb) and its listed distance;
* pi-men: the stored light curve (runs/tess-pi-men-s1/subjects/), the reviewers' marks
  (classifications.csv), the consensus dips (candidates.json) and the limb-darkened joint fit
  (docs/results/pi_men_validation.json, drawn with setuhq.transitfit.transit_model);
* benchmark, feed-noise: docs/results/benchmark_real_tois.json, with the published reference points
  from docs/paper/references.json (each value checked in its source paper; the paper's claims read them too);
* sky-coverage: docs/results/survey_coverage.json, on a Mollweide projection;
* flow-pipeline, architecture: the stored run's counts and the repository's own counts (modules,
  CLI commands, Methods chapters, tests collected by pytest, leaderboard trials);
* methods-strip: setuhq.methods functions (transit_flux, rv_curve, paczynski, airy_intensity,
  lyot_pupil_field) on docs/results/methods_examples.json planets.

Each SVG carries a <desc> that states every number on it, its source file and that file's commit.
The README's alt text for each figure must be that <desc>, word for word; --check enforces it.

GitHub strips web fonts from a README image, so every word is converted to outlines here, from the
OFL fonts in tools/readme-fonts/ (the app's self-hosted Geist, Geist Mono and Unbounded, latin subset, from
site/app/assets/fonts/, decompressed to TrueType). The few symbols those subsets lack (the star,
the Earth sign, lambda, the arrow) are drawn as outlines below; superscript digits are the font's
digits, scaled and raised. The font and SVG helpers follow Kshana's tools/gen_readme_assets.py.

The app screenshots are taken by tools/capture_site_shots.mjs and imported here with --import-shots,
which scales them to one width, encodes them as WebP and writes app/SHOTS.json; this script records
their hashes in MANIFEST.json, so a changed or missing screenshot fails --check.

Usage:
    python3 tools/gen_readme_assets.py                  # write docs/assets/readme/
    python3 tools/gen_readme_assets.py --check          # regenerate in memory; fail on any difference
    python3 tools/gen_readme_assets.py --import-shots DIR   # import a capture_site_shots.mjs run

Needs the package installed (pip install -e .), fontTools (a matplotlib dependency), numpy and
Pillow, and the git history (for each source file's commit; a shallow clone is refused).
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime as _dt
import hashlib
import html
import io
import json
import math
import re
import subprocess
import sys
import tomllib
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from setuhq import benchmark_toi as BT  # noqa: E402
from setuhq import galaxy as GX  # noqa: E402
from setuhq import methods as MX  # noqa: E402
from setuhq import transitfit as TF  # noqa: E402

FONT_DIR = ROOT / "tools" / "readme-fonts"
OUT = ROOT / "docs" / "assets" / "readme"
REL_OUT = "docs/assets/readme"
APP_DIR = OUT / "app"
README = ROOT / "README.md"
MARK_SVG = OUT / "brand" / "setu-mark.svg"
RUN = ROOT / "runs" / "tess-pi-men-s1"

W, H = 1200, 600          # every figure
MX0, MX1 = 40, 1160       # left and right margins
PLOT_TOP, PLOT_BOTTOM = 108, 532
FOOT_RULE, FOOT_Y = 552, 578

SHOT_WIDTH = 1600         # every app screenshot, in pixels
SHOT_QUALITY = 80         # WebP quality

# --------------------------------------------------------------------------------------
# Theme: the app's tokens (src/setuhq/app.py :root and :root[data-theme="light"])
# --------------------------------------------------------------------------------------

DARK = {
    "name": "dark", "bg": "#000000", "panel": "#1C1C1E", "ink": "#F5F5F7", "ink2": "#A1A1A6", "ink3": "#8E8E93",
    "line_rgb": "#FFFFFF", "line_a": (0.08, 0.14, 0.24),
    "known": "#0A84FF", "open": "#FFD60A", "rejected": "#FF453A", "sen": "#64D2FF", "prb": "#BF5AF2",
    "green": "#30D158", "amber": "#FFB340", "coral": "#FF6961", "brand": "#0A84FF", "mark_ink": "#F5F5F7",
    "method": dict(GX.METHOD_COLOUR),
}
LIGHT = {
    "name": "light", "bg": "#F5F5F7", "panel": "#FFFFFF", "ink": "#1D1D1F", "ink2": "#424245", "ink3": "#5E5E63",
    "line_rgb": "#000000", "line_a": (0.08, 0.14, 0.26),
    "known": "#0066CC", "open": "#8A6100", "rejected": "#C9001B", "sen": "#006E99", "prb": "#8944AB",
    "green": "#1F7A35", "amber": "#A05A00", "coral": "#C9001B", "brand": "#0066CC", "mark_ink": "#1D1D1F",
    # the dark method colours, darkened the way the app's light tokens darken its accents
    "method": {"transit": "#006E99", "rv": "#C9001B", "imaging": "#1F7A35", "microlensing": "#8944AB",
               "astrometry": "#8A6100", "timing": "#5856D6", "other": "#6E6E73"},
}
THEMES = (LIGHT, DARK)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def blend(fg: str, bg: str, a: float) -> str:
    """The solid colour of `fg` at opacity `a` over `bg` (the app's rgba() tokens, flattened)."""
    f_, b_ = _hex(fg), _hex(bg)
    return "#%02X%02X%02X" % tuple(round(f_[i] * a + b_[i] * (1 - a)) for i in range(3))


def line(t: dict, level: int = 0, on: str | None = None) -> str:
    return blend(t["line_rgb"], on or t["bg"], t["line_a"][level])


def soft(t: dict, color: str, a: float = 0.14, on: str | None = None) -> str:
    return blend(color, on or t["bg"], a)


# --------------------------------------------------------------------------------------
# Fonts: the variable OFL fonts, instanced per weight; glyph outlines become SVG paths.
# --------------------------------------------------------------------------------------

FONT_FILES = {"sans": "Geist-latin-wght.ttf", "mono": "GeistMono-latin-wght.ttf", "display": "Unbounded-latin-wght.ttf"}
SUPERSCRIPT = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8",
               "⁹": "9", "⁻": "−", "⁺": "+"}
SUP_SCALE, SUP_RISE = 0.62, 360  # scale, and rise in font units (upm 1000)


def _orient(pts: list[tuple[float, float]], ccw: bool = True) -> list[tuple[float, float]]:
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
    return pts if (area > 0) == ccw else pts[::-1]


def _poly(pts, ccw: bool = True) -> str:
    pts = _orient(list(pts), ccw)
    return "M" + "L".join(f"{round(x)} {round(y)}" for x, y in pts) + "Z"


def _circle(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _symbols() -> dict[str, tuple[int, str]]:
    """Outlines (font units, y up) for the few symbols the latin subsets do not carry: advance and path."""
    star = []
    for i in range(10):
        r = 330 if i % 2 == 0 else 135
        a = math.pi / 2 + i * math.pi / 5
        star.append((360 + r * math.cos(a), 300 + r * math.sin(a)))
    earth = (_poly(_circle(330, 265, 262)) + _poly(_circle(330, 265, 204), ccw=False)
             + _poly([(305, 61), (355, 61), (355, 469), (305, 469)]) + _poly([(126, 240), (534, 240), (534, 290), (126, 290)]))
    lam = _poly([(420, 0), (520, 0), (175, 730), (75, 730)]) + _poly([(30, 0), (128, 0), (335, 380), (283, 445)])
    arrow = _poly([(60, 268), (600, 268), (600, 342), (60, 342)]) + _poly([(540, 130), (800, 305), (540, 480)])
    return {"★": (720, _poly(star)), "⊕": (660, earth), "λ": (560, lam), "→": (860, arrow)}


SYMBOLS = _symbols()


class Face:
    """One family at one weight: advances, pair kerning and outlines in font units."""

    _cache: dict[tuple[str, int], "Face"] = {}

    @classmethod
    def get(cls, family: str, weight: int) -> "Face":
        key = (family, weight)
        if key not in cls._cache:
            cls._cache[key] = Face(family, weight)
        return cls._cache[key]

    def __init__(self, family: str, weight: int):
        vf = TTFont(FONT_DIR / FONT_FILES[family])
        self.font = instancer.instantiateVariableFont(vf, {"wght": weight})
        self.id = f"{family[0]}{weight // 100}"
        self.upm = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"].metrics
        self.glyphset = self.font.getGlyphSet()
        self.paths: dict[str, str] = {}
        self._pairs: dict[tuple[str, str], int] = {}
        self._class_tables: list = []
        self._read_kerning()

    def _read_kerning(self) -> None:
        if "GPOS" not in self.font or not self.font["GPOS"].table.LookupList:
            return
        for lookup in self.font["GPOS"].table.LookupList.Lookup:
            for st in lookup.SubTable:
                ltype = lookup.LookupType
                if ltype == 9:
                    ltype, st = st.ExtensionLookupType, st.ExtSubTable
                if ltype != 2:
                    continue
                if st.Format == 1:
                    for i, g1 in enumerate(st.Coverage.glyphs):
                        for pvr in st.PairSet[i].PairValueRecord:
                            v = getattr(pvr.Value1, "XAdvance", 0) if pvr.Value1 else 0
                            if v and (g1, pvr.SecondGlyph) not in self._pairs:
                                self._pairs[(g1, pvr.SecondGlyph)] = v
                elif st.Format == 2:
                    self._class_tables.append((set(st.Coverage.glyphs), st.ClassDef1.classDefs if st.ClassDef1 else {},
                                               st.ClassDef2.classDefs if st.ClassDef2 else {}, st.Class1Record))

    def kern(self, a: str, b: str) -> int:
        if a.startswith("sym") or b.startswith("sym"):
            return 0
        if (a, b) in self._pairs:
            return self._pairs[(a, b)]
        for cov, cd1, cd2, rec in self._class_tables:
            if a in cov:
                v = rec[cd1.get(a, 0)].Class2Record[cd2.get(b, 0)].Value1
                x = getattr(v, "XAdvance", 0) if v else 0
                if x:
                    return x
        return 0

    def glyph(self, ch: str) -> tuple[str, int]:
        g = self.cmap.get(ord(ch))
        if g is not None:
            return g, self.hmtx[g][0]
        if ch in SYMBOLS:
            return "sym" + ch, SYMBOLS[ch][0]
        raise ValueError(f"{self.id}: no glyph for {ch!r} (U+{ord(ch):04X}); add an outline to SYMBOLS or reword")

    def path(self, gname: str) -> str:
        if gname.startswith("sym"):
            return SYMBOLS[gname[3:]][1]
        if gname not in self.paths:
            pen = SVGPathPen(self.glyphset, ntos=lambda v: str(round(v)))
            self.glyphset[gname].draw(pen)
            self.paths[gname] = pen.getCommands()
        return self.paths[gname]

    def layout(self, text: str, size: float, ls_em: float = 0.0):
        """Glyphs as (name, x, scale, rise) in font units, and the advance width in user units."""
        out, x, prev = [], 0.0, None
        track = ls_em * self.upm
        for ch in text:
            scale, rise = 1.0, 0.0
            if ch in SUPERSCRIPT:
                ch, scale, rise = SUPERSCRIPT[ch], SUP_SCALE, SUP_RISE
            g, adv = self.glyph(ch)
            if prev is not None and scale == 1.0 and prev[1] == 1.0:
                x += self.kern(prev[0], g)
            out.append((g, x, scale, rise))
            x += adv * scale + track
            prev = (g, scale)
        return out, (x - (track if text else 0)) * size / self.upm

    def width(self, text: str, size: float, ls_em: float = 0.0) -> float:
        return self.layout(text, size, ls_em)[1]


def tw(text: str, size: float, family: str = "sans", weight: int = 400, ls: float = 0.0) -> float:
    return Face.get(family, weight).width(text, size, ls)


# --------------------------------------------------------------------------------------
# SVG builder
# --------------------------------------------------------------------------------------


def f(v: float) -> str:
    """A compact number: at most two decimals, no trailing zeros."""
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def enc(pts, close: bool = False) -> str:
    """Points as an absolute-then-relative path at 0.1 px."""
    out, last = [], None
    for x, y in pts:
        X, Y = round(x * 10), round(y * 10)
        if last is None:
            out.append(f"M{f(X / 10)} {f(Y / 10)}")
        elif (X, Y) != last:
            out.append(f"l{f((X - last[0]) / 10)} {f((Y - last[1]) / 10)}")
        else:
            continue
        last = (X, Y)
    return "".join(out) + ("z" if close else "")


def enc_dots(pts) -> str:
    """Round dots as zero-length strokes: M x y h0 m dx dy h0 ..."""
    out, last = [], None
    for x, y in pts:
        X, Y = round(x * 10), round(y * 10)
        out.append(f"M{f(X / 10)} {f(Y / 10)}h0" if last is None else f"m{f((X - last[0]) / 10)} {f((Y - last[1]) / 10)}h0")
        last = (X, Y)
    return "".join(out)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class Svg:
    def __init__(self, w: float, h: float, title: str, desc: str):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.body: list[str] = []
        self.defs: list[str] = []
        self.glyph_ids: dict[tuple[str, str], str] = {}
        self._n = 0
        self.runs: list[tuple[float, float, float, float, str]] = []   # x0, x1, baseline, size, text: every text run drawn
        self.panels: list[tuple[float, float, float, float]] = []      # x, y, w, h: every card text may sit in
        self.ellipses: list[tuple[float, float, float, float]] = []    # cx, cy, rx, ry: plot frames text must stay inside

    def uid(self, p: str) -> str:
        self._n += 1
        return f"{p}{self._n}"

    def add(self, s: str) -> None:
        self.body.append(s)

    def rect(self, x, y, w, h, fill="none", stroke=None, sw=1.0, r=0, extra=""):
        s = f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}"' + (f' rx="{f(r)}"' if r else "") + f' fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{f(sw)}"'
        self.add(s + (f" {extra}" if extra else "") + "/>")

    def line(self, x1, y1, x2, y2, stroke, sw=1.0, dash=None, extra=""):
        s = f'<path d="M{f(x1)} {f(y1)}L{f(x2)} {f(y2)}" stroke="{stroke}" stroke-width="{f(sw)}" fill="none"'
        if dash:
            s += f' stroke-dasharray="{dash}"'
        self.add(s + (f" {extra}" if extra else "") + "/>")

    def poly(self, pts, stroke="none", sw=1.0, fill="none", close=False, dash=None, extra=""):
        if len(pts) < 2:
            return
        s = f'<path d="{enc(pts, close)}" fill="{fill}" stroke="{stroke}" stroke-width="{f(sw)}" stroke-linejoin="round" stroke-linecap="round"'
        if dash:
            s += f' stroke-dasharray="{dash}"'
        self.add(s + (f" {extra}" if extra else "") + "/>")

    def dots(self, pts, color, r, opacity=None):
        if pts:
            op = f' stroke-opacity="{f(opacity)}"' if opacity is not None else ""
            self.add(f'<path d="{enc_dots(pts)}" stroke="{color}" stroke-width="{f(2 * r)}" stroke-linecap="round" fill="none"{op}/>')

    def circle(self, cx, cy, r, fill="none", stroke=None, sw=1.0, extra=""):
        s = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{f(sw)}"'
        self.add(s + (f" {extra}" if extra else "") + "/>")

    def text(self, s: str, x: float, y: float, size: float, fill: str, family: str = "sans", weight: int = 400,
             anchor: str = "start", ls: float = 0.0, upper: bool = False) -> float:
        """Draw `s` as outlines with its baseline at y. Returns the advance width."""
        if upper:
            s = s.upper()
        face = Face.get(family, weight)
        glyphs, width = face.layout(s, size, ls)
        x -= width / 2 if anchor == "middle" else width if anchor == "end" else 0
        self.runs.append((x, x + width, y, size, s))
        k = size / face.upm
        uses = []
        for g, gx, sc, rise in glyphs:
            if not face.path(g):
                continue  # a space
            key = (face.id, g)
            if key not in self.glyph_ids:
                gid = f"{face.id}{len(self.glyph_ids):x}"
                self.glyph_ids[key] = gid
                self.defs.append(f'<path id="{gid}" d="{face.path(g)}"/>')
            if sc == 1.0:
                uses.append(f'<use href="#{self.glyph_ids[key]}" x="{round(gx)}"/>')
            else:
                uses.append(f'<use href="#{self.glyph_ids[key]}" transform="translate({round(gx)} {round(rise)}) scale({sc})"/>')
        if uses:
            self.add(f'<g fill="{fill}" transform="translate({f(x)} {f(y)}) scale({k:.5f} {-k:.5f})">{"".join(uses)}</g>')
        return width

    def render(self) -> str:
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(self.w)}" height="{f(self.h)}" '
                f'viewBox="0 0 {f(self.w)} {f(self.h)}" role="img" aria-labelledby="t d">'
                f'<title id="t">{esc(self.title)}</title><desc id="d">{esc(self.desc)}</desc>')
        defs = f'<defs>{"".join(self.defs)}</defs>' if self.defs else ""
        return head + defs + "".join(self.body) + "</svg>\n"


# --------------------------------------------------------------------------------------
# The figure frame and shared pieces
# --------------------------------------------------------------------------------------


def frame(s: Svg, t: dict, eyebrow: str, title: str, footer: str, color: str | None = None) -> None:
    """The card every figure sits on: background, border, eyebrow, title and the source footer."""
    s.rect(0, 0, s.w, s.h, fill=t["bg"], r=20)
    s.rect(0.5, 0.5, s.w - 1, s.h - 1, stroke=line(t, 1), sw=1, r=20)
    s.rect(MX0, 40, 8, 8, fill=color or t["known"], r=2)
    s.text(eyebrow, MX0 + 18, 48, 11.5, t["ink3"], "mono", 500, ls=0.12, upper=True)
    s.text(title, MX0, 82, 24, t["ink"], "sans", 600, ls=-0.015)
    s.line(MX0, FOOT_RULE, MX1, FOOT_RULE, line(t, 0))
    s.text(footer, MX0, FOOT_Y, 10.5, t["ink3"], "mono", 400)


def panel(s: Svg, t: dict, x, y, w, h, r=14) -> None:
    s.panels.append((x, y, w, h))
    s.rect(x, y, w, h, fill=t["panel"], stroke=line(t, 0, t["panel"]), sw=1, r=r)


def label_tag(s: Svg, t: dict, x, y, text: str, color: str) -> float:
    """A small pill naming what a drawing is (real data, model, illustration), as the app labels it."""
    size = 9.5
    w_ = tw(text.upper(), size, "mono", 500, 0.08) + 24
    s.rect(x, y - 13, w_, 18, fill=t["panel"], stroke=line(t, 1, t["panel"]), r=9)
    s.circle(x + 9, y - 4, 2.6, fill=color)
    s.text(text, x + 16, y, size, t["ink2"], "mono", 500, ls=0.08, upper=True)
    return w_


def nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10)), key=lambda st: abs(span / st - n))
    v, out = math.ceil(lo / step - 1e-9) * step, []
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def fmt_int(n: int) -> str:
    return f"{n:,}"


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


UNBREAKABLE = re.compile(r"\S+ [<>≤≥=] \S+(?: (?:d|h|ppm|R⊕|%))?(?=[\s,;.)]|$)")


def wrap(text: str, width: float, size: float, family="sans", weight=400) -> list[str]:
    """Greedy word wrap; a comparison such as "P < 100 d" stays on one line."""
    face = Face.get(family, weight)
    text = UNBREAKABLE.sub(lambda m: m.group(0).replace(" ", "\x00"), text)
    lines, cur = [], ""
    for word in (w.replace("\x00", " ") for w in text.split(" ") if w):
        trial = f"{cur} {word}".strip()
        if cur and face.width(trial, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def paragraph(s: Svg, text: str, x, y, width, size, fill, lh=1.45, family="sans", weight=400) -> float:
    lines = wrap(text, width, size, family, weight)
    for i, ln in enumerate(lines):
        s.text(ln, x, y + i * size * lh, size, fill, family, weight)
    return y + len(lines) * size * lh


def sup_exp(e: int) -> str:
    return str(e).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))


def arrow(s: Svg, t: dict, pts, color: str | None = None, sw: float = 1.4) -> None:
    color = color or t["ink3"]
    s.poly(pts, stroke=color, sw=sw)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    ang = math.atan2(y2 - y1, x2 - x1)
    a, L = math.radians(26), 8
    p1 = (x2 - L * math.cos(ang - a), y2 - L * math.sin(ang - a))
    p2 = (x2 - L * math.cos(ang + a), y2 - L * math.sin(ang + a))
    s.poly([p1, (x2, y2), p2], fill=color, close=True, stroke=color, sw=1)


# --------------------------------------------------------------------------------------
# Provenance: each source file's commit
# --------------------------------------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def history_problem() -> str | None:
    """Why the git history this tool needs is missing (a ZIP download, a copy, a shallow clone), or None."""
    try:
        top = _git("rev-parse", "--show-toplevel")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "this copy has no git history (for example a ZIP download, or git is not installed)"
    if Path(top).resolve() != ROOT.resolve():
        return f"this copy is not its own git repository (the enclosing repository is {top})"
    if _git("rev-parse", "--is-shallow-repository") == "true":
        return "this is a shallow clone"
    return None


@lru_cache(maxsize=None)
def commit_of(*paths: str) -> str:
    """The short hash of the last commit that changed any of `paths` (repository-relative)."""
    h = _git("log", "-1", "--format=%h", "--abbrev=7", "--", *paths)
    if not h:
        sys.exit(f"gen_readme_assets: {', '.join(paths)} is not committed; commit the data first")
    return h


def sha256_file(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# The logo and the square mark
# --------------------------------------------------------------------------------------


def _path_bbox(d: str) -> tuple[float, float, float, float]:
    """Bounding box of a path's points and control points (enough to frame the mark)."""
    toks = re.findall(r"[MmCcLlHhVvZzSsQq]|-?\d*\.?\d+(?:e-?\d+)?", d)
    xs, ys, x, y, sx, sy, cmd, i = [], [], 0.0, 0.0, 0.0, 0.0, "M", 0
    nargs = {"M": 2, "L": 2, "C": 6, "S": 4, "Q": 4, "H": 1, "V": 1}
    while i < len(toks):
        tk = toks[i]
        if tk.isalpha():
            cmd = tk
            i += 1
            if cmd in "Zz":
                x, y = sx, sy
            continue
        up, rel = cmd.upper(), cmd.islower()
        args = [float(v) for v in toks[i:i + nargs[up]]]
        i += nargs[up]
        if up == "H":
            x = x + args[0] if rel else args[0]
        elif up == "V":
            y = y + args[0] if rel else args[0]
        else:
            pts = [(args[j] + (x if rel else 0), args[j + 1] + (y if rel else 0)) for j in range(0, len(args), 2)]
            for px, py in pts:
                xs.append(px)
                ys.append(py)
            x, y = pts[-1]
            if up == "M":
                sx, sy = x, y
                cmd = "l" if rel else "L"
        xs.append(x)
        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


@lru_cache(maxsize=1)
def mark_paths() -> tuple[list[str], tuple[float, float, float, float]]:
    """The mark's paths (in the file's 0.1-unit, y-up space) and their box in the 1254-unit viewBox."""
    txt = MARK_SVG.read_text(encoding="utf-8")
    paths = re.findall(r'<path d="([^"]+)"', txt)
    if not paths or "translate(0,1254) scale(0.1,-0.1)" not in txt:
        sys.exit(f"gen_readme_assets: unexpected mark file {MARK_SVG}")
    boxes = [_path_bbox(d) for d in paths]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    # to viewBox units: X = x/10, Y = 1254 - y/10
    return paths, (x0 / 10, 1254 - y1 / 10, x1 / 10, 1254 - y0 / 10)


def draw_mark(s: Svg, x: float, y: float, h: float, color: str) -> float:
    """The mark scaled to height h with its top-left at (x, y). Returns its width."""
    paths, (bx0, by0, bx1, by1) = mark_paths()
    k = h / (by1 - by0)
    tr = f"translate({f(x - bx0 * k)} {f(y - by0 * k)}) scale({k:.6f}) translate(0 1254) scale(0.1 -0.1)"
    s.add(f'<g fill="{color}" transform="{tr}">' + "".join(f'<path d="{d}"/>' for d in paths) + "</g>")
    return (bx1 - bx0) * k


# --------------------------------------------------------------------------------------
# The SetuHQ brand: the mark, the wordmark with the transit Q, icons, favicon, social card
# --------------------------------------------------------------------------------------

BRAND_DIR = ROOT / "docs" / "assets" / "brand"
BRAND = {
    "light": {"ink": "#0A1226", "blue": "#0071E3", "planet": "#64D2FF", "bg": "#FFFFFF"},
    "dark": {"ink": "#F5F5F7", "blue": "#0A84FF", "planet": "#64D2FF", "bg": "#000000"},
}
NAVY = "#0A1226"
SETU_TRACK = -1 / 64          # letter-spacing of "Setu", in em
HQ_GAP = 0.11                 # space between "Setu" and "H", in em


@lru_cache(maxsize=1)
def q_geometry() -> dict:
    """The transit Q, in font units (y up, baseline 0), matched to Unbounded 300's O: the same height
    (with the O's overshoot), the O's mean stroke, its side bearings. A ring (the star), a planet dot
    crossing its face toward the upper left, and the Q's tail at the lower right."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen

    face = Face.get("display", 300)
    g = face.cmap[ord("O")]
    bp = BoundsPen(face.glyphset)
    face.glyphset[g].draw(bp)
    x0, y0, x1, y1 = bp.bounds
    rp = RecordingPen()
    face.glyphset[g].draw(rp)
    contours, cur = [], []
    for op, args in rp.value:
        cur += list(args)
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    inner = min(contours, key=lambda c: max(p[0] for p in c) - min(p[0] for p in c))
    ix0, ix1 = min(p[0] for p in inner), max(p[0] for p in inner)
    iy0, iy1 = min(p[1] for p in inner), max(p[1] for p in inner)
    stroke = ((ix0 - x0) + (x1 - ix1) + (iy0 - y0) + (y1 - iy1)) / 4
    outer_r = (y1 - y0) / 2
    r = outer_r - stroke / 2                    # the ring's centre line
    lsb = face.hmtx[g][1]
    cx, cy = lsb + outer_r, (y0 + y1) / 2
    d45 = math.sqrt(0.5)
    tail = ((cx + 0.6 * r * d45, cy - 0.6 * r * d45), (cx + 1.55 * r * d45, cy - 1.55 * r * d45))
    advance = tail[1][0] + stroke / 2 + lsb
    return {"cx": cx, "cy": cy, "r": r, "stroke": stroke, "planet": (cx - 0.24 * r, cy + 0.19 * r, 0.3 * r),
            "tail": tail, "advance": advance, "top": y1, "bottom": y0}


def draw_q(s: Svg, x: float, base: float, size: float, ring: str, planet: str) -> float:
    """The transit Q as SVG geometry (circle, circle, rounded line) at pen position x on baseline `base`."""
    q = q_geometry()
    k = size / 1000
    X = lambda u: x + u * k  # noqa: E731
    Y = lambda v: base - v * k  # noqa: E731
    s.circle(X(q["cx"]), Y(q["cy"]), q["r"] * k, stroke=ring, sw=q["stroke"] * k)
    px, py, pr = q["planet"]
    s.circle(X(px), Y(py), pr * k, fill=planet)
    (ax, ay), (bx, by) = q["tail"]
    s.line(X(ax), Y(ay), X(bx), Y(by), ring, q["stroke"] * k, extra='stroke-linecap="round"')
    return q["advance"] * k


def wordmark_width(size: float) -> float:
    return (tw("Setu", size, "display", 600, SETU_TRACK) + HQ_GAP * size + tw("H", size, "display", 300)
            + q_geometry()["advance"] * size / 1000)


def draw_wordmark(s: Svg, x: float, base: float, size: float, ink: str, blue: str, planet: str) -> float:
    x0 = x
    x += s.text("Setu", x, base, size, ink, "display", 600, ls=SETU_TRACK) + HQ_GAP * size
    x += s.text("H", x, base, size, blue, "display", 300)
    x += draw_q(s, x, base, size, blue, planet)
    return x - x0


def mark_box() -> tuple[float, float]:
    _, (bx0, by0, bx1, by1) = mark_paths()
    return bx1 - bx0, by1 - by0


LOGO_DESC = ("SetuHQ: the Setu mark, a flowing S of two paths with a dashed centre line (setu, the bridge), beside the "
             "wordmark SetuHQ, whose Q is a star with a planet crossing its face: a transit.")
WORDMARK_DESC = "The SetuHQ wordmark: Setu, then HQ in blue, whose Q is a star with a planet crossing its face: a transit."
ICON_DESC = "The SetuHQ app icon: the transit Q, a blue ring (a star) with a cyan planet crossing its face, on a rounded square."


def brand_lockup(theme: str) -> Svg:
    c = BRAND[theme]
    size = 96
    cap = 750 * size / 1000
    mw, mh = mark_box()
    mark_h = cap * 1.72
    mark_w = mw * mark_h / mh
    gap = 0.3 * size
    pad = 4
    top_pad = (mark_h - cap) / 2 + pad
    W_ = math.ceil(pad + mark_w + gap + wordmark_width(size) + pad)
    H_ = math.ceil(mark_h + 2 * pad)
    s = Svg(W_, H_, "SetuHQ", LOGO_DESC)
    draw_mark(s, pad, pad, mark_h, c["ink"])
    draw_wordmark(s, pad + mark_w + gap, top_pad + cap, size, c["ink"], c["blue"], c["planet"])
    return s


def brand_wordmark(theme: str) -> Svg:
    c = BRAND[theme]
    size = 96
    q = q_geometry()
    top, bottom = q["top"] * size / 1000, -q["bottom"] * size / 1000
    pad = 4
    s = Svg(math.ceil(wordmark_width(size) + 2 * pad), math.ceil(top + bottom + 2 * pad), "SetuHQ", WORDMARK_DESC)
    draw_wordmark(s, pad, pad + top, size, c["ink"], c["blue"], c["planet"])
    return s


def _q_centred(s: Svg, cx: float, cy: float, height: float, ring: str, planet: str) -> None:
    """The Q alone, its ring centred on (cx, cy) (the tail hangs outside the ring, as in the letter)."""
    q = q_geometry()
    size = height / (2 * (q["r"] + q["stroke"] / 2)) * 1000
    k = size / 1000
    # shift the whole Q up-left by half the tail's overhang so the glyph, tail included, is optically centred
    over = (q["tail"][1][0] + q["stroke"] / 2 - (q["cx"] + q["r"] + q["stroke"] / 2)) * k / 2
    draw_q(s, cx - q["cx"] * k - over, cy + q["cy"] * k - over, size, ring, planet)


def brand_icon(bg: str) -> Svg:
    s = Svg(512, 512, "SetuHQ", ICON_DESC)
    s.rect(0, 0, 512, 512, fill=bg, r=115)
    _q_centred(s, 256, 256, 300, BRAND["dark"]["blue"], BRAND["dark"]["planet"])
    return s


def brand_favicon() -> str:
    """The transit Q for a browser tab, following the system theme (a <style> media query, which browsers honour in favicons)."""
    s = Svg(64, 64, "SetuHQ", "The SetuHQ favicon: the transit Q, blue on light tabs and bright blue on dark tabs.")
    _q_centred(s, 32, 32, 50, "#RING#", BRAND["light"]["planet"])
    svg = s.render()
    style = ("<style>.r{stroke:%s}@media (prefers-color-scheme: dark){.r{stroke:%s}}</style>"
             % (BRAND["light"]["blue"], BRAND["dark"]["blue"]))
    svg = svg.replace('stroke="#RING#"', 'class="r"')
    return svg.replace("</desc>", "</desc>" + style, 1)


def brand_social() -> Svg:
    c = BRAND["dark"]
    s = Svg(1200, 630, "SetuHQ", "The SetuHQ social card: the SetuHQ logo on navy, with the line The open exoplanet observatory: "
            "from public sky data to reviewed, explained candidates, and setuhq.com.")
    s.rect(0, 0, 1200, 630, fill=NAVY)
    size = 112
    cap = 750 * size / 1000
    mw, mh = mark_box()
    mark_h = cap * 1.72
    mark_w = mw * mark_h / mh
    gap = 0.3 * size
    total = mark_w + gap + wordmark_width(size)
    x = (1200 - total) / 2
    ytop = 168
    draw_mark(s, x, ytop, mark_h, c["ink"])
    draw_wordmark(s, x + mark_w + gap, ytop + (mark_h - cap) / 2 + cap, size, c["ink"], c["blue"], c["planet"])
    s.text("The open exoplanet observatory", 600, 398, 34, c["ink"], "sans", 500, anchor="middle", ls=-0.01)
    s.text("from public sky data to reviewed, explained candidates", 600, 442, 24, "#A1A1A6", "sans", 400, anchor="middle")
    s.text("setuhq.com", 600, 532, 18, "#8E8E93", "mono", 500, anchor="middle", ls=0.06)
    return s


def brand_assets() -> dict[str, bytes]:
    """docs/assets/brand/: every brand file, keyed by its path from the repository root."""
    b = "docs/assets/brand/"
    out = {}
    for th in ("light", "dark"):
        out[f"{b}setuhq-logo-{th}.svg"] = brand_lockup(th).render().encode()
        out[f"{b}setuhq-wordmark-{th}.svg"] = brand_wordmark(th).render().encode()
    out[f"{b}setuhq-icon-black.svg"] = brand_icon("#000000").render().encode()
    out[f"{b}setuhq-icon-navy.svg"] = brand_icon(NAVY).render().encode()
    out[f"{b}setuhq-favicon.svg"] = brand_favicon().encode()
    out[f"{b}setuhq-social-card.svg"] = brand_social().render().encode()
    return out


# --------------------------------------------------------------------------------------
# Hero: every known exoplanet with a distance, around the Sun
# --------------------------------------------------------------------------------------

HERO_SRC = "docs/results/exoplanet_map.json"


def hero_data() -> dict:
    m = load_json(HERO_SRC)
    P = m["planets"]
    n = len(P["name"])
    pts = []
    for i in range(n):
        lon, _ = GX.galactic_lb(P["ra"][i], P["dec"][i])
        pts.append((lon, P["dist_pc"][i] * GX.LY_PER_PC, P["method"][i]))
    counts = Counter(p[2] for p in pts)
    dmax = max(p[1] for p in pts)
    dmin = min(p[1] for p in pts)
    near = min(range(n), key=lambda i: P["dist_pc"][i])
    pimen = [i for i in range(n) if P["host"][i] == "pi Men"]
    return {"m": m, "pts": pts, "counts": counts, "dmax": dmax, "dmin": dmin, "nearest": (P["name"][near], P["dist_pc"][near] * GX.LY_PER_PC),
            "pimen": (GX.galactic_lb(P["ra"][pimen[0]], P["dec"][pimen[0]])[0], P["dist_pc"][pimen[0]] * GX.LY_PER_PC, len(pimen)),
            "commit": commit_of(HERO_SRC)}


def hero_desc(d: dict) -> str:
    m, c = d["m"], d["counts"]
    order = sorted(m["methods"], key=lambda k: -c[k])
    per = "; ".join(f"{m['method_label'][k]} {fmt_int(c[k])}" for k in order)
    return (f"Every known exoplanet with a distance, around the Sun: {fmt_int(m['counts']['kept'])} of the {fmt_int(m['counts']['rows'])} "
            f"planets in {m['source_short']} (fetched {m['fetched_at'][:10]}), around {fmt_int(m['counts']['hosts'])} host stars, seen from above "
            f"the Galactic plane with the Sun at the centre and the Galactic centre (longitude 0°) at the top. Angle is galactic longitude; "
            f"distance from the centre is the listed distance on a logarithmic scale, with rings at 10, 100, 1,000 and 10,000 light-years; "
            f"galactic latitude is dropped. Colour is the first detection method listed: {per}. "
            f"The {fmt_int(m['counts']['dropped_no_distance'])} planets without a distance are not drawn. pi Men, host of pi Men c and "
            f"the star of SetuHQ's stored run, is marked at {d['pimen'][1]:.1f} light-years. No Milky Way is drawn: every point is a "
            f"catalogue position, not an illustration. Source: {HERO_SRC}, commit {d['commit']}.")


def hero(t: dict, d: dict) -> Svg:
    m, c = d["m"], d["counts"]
    s = Svg(W, H, "Every known exoplanet with a distance, around the Sun", hero_desc(d))
    frame(s, t, "Galaxy · exoplanet.eu, fetched " + m["fetched_at"][:10],
          "Every known exoplanet with a distance, around the Sun",
          f"Source: {HERO_SRC} ({m['source_short']}, {fmt_int(m['counts']['kept'])} of {fmt_int(m['counts']['rows'])} planets) · commit {d['commit']}",
          t["known"])
    # the polar plot
    cx, cy, R = 822, 322, 206
    lo, hi = 0.0, math.ceil(math.log10(d["dmax"]))   # 1 ly at the centre, the next decade at the rim

    def pos(lon, dist_ly):
        r = R * min(1.0, max(0.0, (math.log10(max(dist_ly, 1.0)) - lo) / (hi - lo)))
        a = math.radians(lon)
        return cx - r * math.sin(a), cy - r * math.cos(a)

    s.circle(cx, cy, R, fill=t["panel"], stroke=line(t, 1, t["panel"]))
    for dec in range(1, int(hi)):
        rr = R * (dec - lo) / (hi - lo)
        s.circle(cx, cy, rr, stroke=line(t, 1, t["panel"]), sw=1)
    for k in range(12):
        a = math.radians(30 * k)
        s.line(cx - R * 0.06 * math.sin(a), cy - R * 0.06 * math.cos(a), cx - R * math.sin(a), cy - R * math.cos(a),
               line(t, 0, t["panel"]), 1)
    order = sorted(m["methods"], key=lambda k: -c[k])
    for mt in order:
        pts = [pos(lon, dl) for lon, dl, mm in d["pts"] if mm == mt]
        s.dots(pts, t["method"][mt], 1.45, opacity=0.9)
    # ring labels on the lower-right diagonal, over a panel-coloured chip
    for dec in range(1, int(hi)):
        rr = R * (dec - lo) / (hi - lo)
        lab = f"{fmt_int(10 ** dec)} ly"
        lx, ly = cx + rr * math.sin(math.radians(135)), cy - rr * math.cos(math.radians(135))
        wl = tw(lab, 10.5, "mono", 500)
        s.rect(lx - wl / 2 - 5, ly - 9, wl + 10, 16, fill=t["panel"], r=8)
        s.text(lab, lx, ly + 3.5, 10.5, t["ink2"], "mono", 500, anchor="middle")
    # the Sun and pi Men
    s.circle(cx, cy, 4.2, fill=t["amber"], stroke=t["panel"], sw=1.5)
    s.text("Sun", cx + 8, cy + 15, 11, t["ink"], "sans", 600)
    px, py = pos(d["pimen"][0], d["pimen"][1])
    s.circle(px, py, 7, stroke=t["ink"], sw=1.3)
    s.line(px + 5, py - 5, px + 34, py - 30, t["ink"], 1)
    lab = f"pi Men · {d['pimen'][1]:.1f} ly"
    s.rect(px + 32, py - 44, tw(lab, 11, "sans", 600) + 12, 20, fill=t["panel"], stroke=line(t, 1, t["panel"]), r=10)
    s.text(lab, px + 38, py - 30, 11, t["ink"], "sans", 600)
    # compass
    s.text("l = 0° · toward the Galactic centre", cx, cy - R - 10, 10.5, t["ink2"], "mono", 500, anchor="middle")
    s.text("l = 180°", cx, cy + R + 20, 10.5, t["ink2"], "mono", 500, anchor="middle")
    s.text("l = 90°", cx - R - 10, cy + 4, 10.5, t["ink2"], "mono", 500, anchor="end")
    s.text("l = 270°", cx + R + 10, cy + 4, 10.5, t["ink2"], "mono", 500)
    # the left column: the count and the legend
    y = 150
    s.text(fmt_int(m["counts"]["kept"]), MX0, y + 34, 52, t["ink"], "sans", 600, ls=-0.03)
    s.text("planets placed", MX0, y + 60, 15, t["ink2"], "sans", 500)
    s.text(f"of {fmt_int(m['counts']['rows'])} in {m['source_short']}; {fmt_int(m['counts']['dropped_no_distance'])} have no distance",
           MX0, y + 82, 12, t["ink3"], "sans", 400)
    y = 268
    s.text("First detection method", MX0, y, 10.5, t["ink3"], "mono", 500, ls=0.1, upper=True)
    y += 12
    for mt in order:
        y += 22
        s.circle(MX0 + 5, y - 4, 4.5, fill=t["method"][mt])
        s.text(m["method_label"][mt], MX0 + 18, y, 13, t["ink"], "sans", 500)
        s.text(fmt_int(c[mt]), MX0 + 300, y, 12, t["ink2"], "mono", 400, anchor="end")
    y += 30
    paragraph(s, "Angle: galactic longitude. Radius: the listed distance, log scale. Latitude dropped; no Milky Way drawn.",
              MX0, y, 300, 11.5, t["ink3"])
    return s


# --------------------------------------------------------------------------------------
# pi Men c: the stored light curve, the reviewers' marks and the limb-darkened fit
# --------------------------------------------------------------------------------------

PIMEN_SRC = ("runs/tess-pi-men-s1", "docs/results/pi_men_validation.json")
REVIEWER_ORDER = [("volunteer-sensitive", "Probe · Sensitive", "prb"), ("volunteer-typical", "Probe · Typical", "prb"),
                  ("volunteer-cautious", "Probe · Cautious", "prb"), ("claude-volunteer", "Sentinel · Volunteer", "sen"),
                  ("claude-skeptic", "Sentinel · Skeptic", "sen")]


@lru_cache(maxsize=1)
def pimen_data() -> dict:
    v = load_json("docs/results/pi_men_validation.json")
    cands = load_json("runs/tess-pi-men-s1/candidates.json")
    subs = []
    for sid in sorted({c["subject_id"] for c in cands}):
        subs.append(load_json(f"runs/tess-pi-men-s1/subjects/{sid}.json"))
    subs.sort(key=lambda s_: s_["start"])
    t = np.concatenate([np.array(s_["time"]) for s_ in subs])
    fl = np.concatenate([np.array(s_["flux"]) for s_ in subs])
    marks: dict[str, list] = {}
    sentinel_rows: dict[tuple[str, str], dict] = {}
    with open(RUN / "classifications.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ann = json.loads(row["annotations"])
            spans = [(a["t_start"], a["t_end"]) for task in ann if task["task"] == "T0" for a in task["value"]]
            marks.setdefault(row["user_name"], []).extend(spans)
            meta = json.loads(row["metadata"])
            sentinel_rows[(row["user_name"], row["subject_ids"])] = {"label": row["label"], "confidence": meta.get("confidence"),
                                                                      "spans": spans}
    events = []
    for c in sorted(cands, key=lambda c_: c_["t_center"]):
        flags = [x for x in c["flags"].split(";") if x]
        status = "rejected" if not c["passed"] else "open" if "off_ephemeris" in flags else "known"
        events.append({"t": c["t_center"], "status": status, "depth": c["depth_ppm"], "snr": c["snr"], "flags": flags,
                       "dur": c["duration_hours"]})
    jf = v["joint_fit"]
    cad = float(np.median(np.diff(t)))
    manifest = load_json("runs/tess-pi-men-s1/manifest.json")
    return {"v": v, "t": t, "f": fl, "subs": subs, "marks": marks, "events": events, "jf": jf, "cad": cad, "cands": cands,
            "sentinel_rows": sentinel_rows, "weights": manifest["weights"], "manifest": manifest, "commit": commit_of(*PIMEN_SRC)}


def pimen_desc(d: dict) -> str:
    v, jf = d["v"], d["jf"]
    r = v["ratios_vs_huang_2018"]
    h = v["huang_2018"]
    ev = d["events"]
    known = [e for e in ev if e["status"] == "known"]
    opn = [e for e in ev if e["status"] == "open"]
    rej = [e for e in ev if e["status"] == "rejected"]
    nmarks = {rid: len(d["marks"].get(rid, [])) for rid, _, _ in REVIEWER_ORDER}
    return ("pi Men c in TESS sector 1, from SetuHQ's stored run. Left: the stored light curve of pi Men (TIC 261136679), "
            f"{fmt_int(len(d['t']))} points in 10-minute bins over BTJD {d['t'][0]:.1f} to {d['t'][-1]:.1f}, in parts per million, "
            f"with the {len(ev)} consensus dips: {len(known)} passed and on pi Men c's published ephemeris (known, at BTJD "
            + ", ".join(f"{e['t']:.2f}" for e in known)
            + f"), {len(opn)} passed but off the ephemeris and flagged (open, at BTJD " + ", ".join(f"{e['t']:.2f}" for e in opn)
            + f"), and {len(rej)} rejected by vetting (at BTJD " + ", ".join(f"{e['t']:.2f}" for e in rej) + "). "
            "Below it, each reviewer's marks as stored: "
            + "; ".join(f"{lab} {nmarks[rid]}" for rid, lab, _ in REVIEWER_ORDER)
            + " spans. Right: the points folded on the joint limb-darkened fit of the five epochs "
            f"(period {jf['period_days']:.4f} d), from 5 hours before to 5 hours after mid-transit, with 20-minute means and the fitted model "
            f"integrated over the 10-minute bins. Rp/R★ = {jf['k']:.4f} ± {jf['k_err']:.4f}, {r['k']:.2f} times Huang et al. 2018's {h['pl_ratror']}; "
            f"T14 = {jf['t14_hours']:.2f} ± {jf['t14_err_hours']:.2f} h, {r['duration']:.2f} times Huang's {h['pl_trandur']} h; "
            f"model depth {jf['depth_ppm']:.0f} ± {jf['depth_err_ppm']:.0f} ppm. A known planet recovered, not a discovery. "
            f"Sources: runs/tess-pi-men-s1 (subjects, classifications.csv, candidates.json) and docs/results/pi_men_validation.json, commit {d['commit']}.")


def pimen(t: dict, d: dict) -> Svg:
    v, jf = d["v"], d["jf"]
    r = v["ratios_vs_huang_2018"]
    s = Svg(W, H, "pi Men c: the stored light curve, the reviewers' marks and the limb-darkened fit", pimen_desc(d))
    frame(s, t, "Transit case · TESS sector 1 · real data", "pi Men c, found by the panel and fitted",
          f"Source: runs/tess-pi-men-s1 (subjects, classifications, candidates) · docs/results/pi_men_validation.json · commit {d['commit']}",
          t["known"])
    stat = {"known": t["known"], "open": t["open"], "rejected": t["rejected"]}
    # ---- left: the whole run
    panel(s, t, MX0, PLOT_TOP, 740, PLOT_BOTTOM - PLOT_TOP)
    X0, X1 = 196, 760
    T0, T1 = math.floor(d["t"][0]), math.ceil(d["t"][-1])
    tx = lambda tt: X0 + (tt - T0) / (T1 - T0) * (X1 - X0)  # noqa: E731
    LY0, LY1, P0, P1 = 140, 290, -500.0, 300.0   # ppm range, top value P1
    ly = lambda ppm: LY0 + (P1 - min(P1, max(P0, ppm))) / (P1 - P0) * (LY1 - LY0)  # noqa: E731
    label_tag(s, t, MX0 + 18, PLOT_TOP + 24, "Real data · stored points", t["known"])
    s.text("brightness, ppm", X1, PLOT_TOP + 24, 10.5, t["ink3"], "mono", 500, anchor="end")
    for tick in (-400, -200, 0, 200):
        yy = ly(tick)
        s.line(X0, yy, X1, yy, line(t, 0, t["panel"]))
        s.text(f"{tick:+d}".replace("+0", "0").replace("-", "−"), X0 - 8, yy + 3.5, 10, t["ink3"], "mono", 400, anchor="end")
    ppm = (d["f"] - 1.0) * 1e6
    s.dots([(tx(a), ly(b)) for a, b in zip(d["t"], ppm)], soft(t, t["ink"], 0.45, t["panel"]), 0.9)
    # event markers
    letters = "ABCDEFGHIJ"
    for i, e in enumerate(d["events"]):
        xx = tx(e["t"])
        s.line(xx, LY1 + 6, xx, LY1 + 14, stat[e["status"]], 2)
        s.text(letters[i], xx, LY1 + 27, 10, stat[e["status"]], "mono", 600, anchor="middle")
    # reviewer lanes
    lane_y0, lane_h = 340, 24
    for j, (rid, lab, kind) in enumerate(REVIEWER_ORDER):
        yy = lane_y0 + j * lane_h
        s.text(lab, MX0 + 18, yy + 4, 11.5, t[kind] if kind == "sen" else t["prb"], "sans", 500)
        s.line(X0, yy, X1, yy, line(t, 0, t["panel"]), 4, extra='stroke-linecap="round"')
        for a, b in d["marks"].get(rid, []):
            s.line(tx(a), yy, max(tx(b), tx(a) + 2.5), yy, t[kind], 6, extra='stroke-linecap="round"')
    # time axis
    ay = lane_y0 + len(REVIEWER_ORDER) * lane_h + 4
    for tick in range(T0 - T0 % 5 + 5, T1 + 1, 5):
        s.text(str(tick), tx(tick), ay + 10, 10, t["ink3"], "mono", 400, anchor="middle")
    s.text("Time (BTJD)", X1, ay + 30, 10.5, t["ink3"], "mono", 500, anchor="end")
    # legend
    lx = MX0 + 18
    for key, lab in (("known", "on pi Men c's ephemeris"), ("open", "off it, flagged"), ("rejected", "rejected")):
        s.rect(lx, ay + 21, 10, 10, fill=stat[key], r=2)
        lx += 16 + s.text(lab, lx + 16, ay + 30, 11, t["ink2"], "sans", 500) + 18
    # ---- right: the folded transit and the fit
    RX0, RX1 = 800, MX1
    panel(s, t, RX0, PLOT_TOP, RX1 - RX0, PLOT_BOTTOM - PLOT_TOP)
    label_tag(s, t, RX0 + 18, PLOT_TOP + 24, "Real data + fitted model", t["known"])
    FX0, FX1, FY0, FY1 = RX0 + 52, RX1 - 18, 150, 330
    HW, Q0, Q1 = 5.0, -450.0, 200.0
    fx = lambda hrs: FX0 + (hrs + HW) / (2 * HW) * (FX1 - FX0)  # noqa: E731
    fy = lambda p: FY0 + (Q1 - min(Q1, max(Q0, p))) / (Q1 - Q0) * (FY1 - FY0)  # noqa: E731
    P, tc = jf["period_days"], jf["t0"]
    ph = ((d["t"] - tc + P / 2) % P - P / 2) * 24
    sel = np.abs(ph) <= HW
    for tick in (-400, -200, 0, 200):
        yy = fy(tick)
        s.line(FX0, yy, FX1, yy, line(t, 0, t["panel"]))
        s.text(f"{tick}".replace("-", "−"), FX0 - 8, yy + 3.5, 10, t["ink3"], "mono", 400, anchor="end")
    for hrs in (-4, -2, 0, 2, 4):
        s.text(f"{hrs:+d}".replace("+0", "0").replace("-", "−"), fx(hrs), FY1 + 16, 10, t["ink3"], "mono", 400, anchor="middle")
    s.text("hours from mid-transit", FX1, FY1 + 34, 10.5, t["ink3"], "mono", 500, anchor="end")
    s.dots([(fx(a), fy(b)) for a, b in zip(ph[sel], ppm[sel])], soft(t, t["ink"], 0.4, t["panel"]), 1.2)
    edges = np.arange(-HW, HW + 1e-9, 1 / 3)
    means = []
    for a, b in zip(edges[:-1], edges[1:]):
        m_ = (ph >= a) & (ph < b)
        if m_.sum() >= 3:
            means.append((fx((a + b) / 2), fy(float(np.mean(ppm[m_])))))
    hh = np.linspace(-HW, HW, 601)
    model = TF.transit_model(tc + hh / 24, tc, jf["k"], jf["t14_hours"] / 24, jf["b"], P, jf["u1"], jf["u2"],
                             exptime=d["cad"], supersample=5)
    oot = float(np.median(ppm[sel & (np.abs(ph) > jf["t14_hours"] / 2 + 0.5)]))
    d["oot_ppm"] = oot
    s.poly([(fx(a), fy((b - 1) * 1e6 + oot)) for a, b in zip(hh, model)], stroke=t["known"], sw=2.2)
    s.dots(means, t["ink"], 2.6)
    # the two numbers
    by = 400
    h = v["huang_2018"]
    for i, (name, val, ratio, ref) in enumerate((
            ("Rp/R★", f"{jf['k']:.4f} ± {jf['k_err']:.4f}", r["k"], f"Huang 2018: {h['pl_ratror']}"),
            ("T14", f"{jf['t14_hours']:.2f} ± {jf['t14_err_hours']:.2f} h", r["duration"], f"Huang 2018: {h['pl_trandur']} h"))):
        x = RX0 + 18 + i * 172
        s.text(name, x, by, 11, t["ink3"], "mono", 500, ls=0.06)
        s.text(f"{ratio:.2f}", x, by + 40, 38, t["ink"], "sans", 600, ls=-0.03)
        s.text("× Huang 2018", x + tw(f"{ratio:.2f}", 38, "sans", 600, -0.03) + 6, by + 40, 11, t["ink2"], "sans", 500)
        s.text(val, x, by + 64, 11.5, t["ink2"], "mono", 400)
        s.text(ref, x, by + 82, 10.5, t["ink3"], "mono", 400)
    s.text(f"Model depth {jf['depth_ppm']:.0f} ± {jf['depth_err_ppm']:.0f} ppm, drawn at the out-of-transit level",
           RX0 + 18, PLOT_BOTTOM - 14, 10.5, t["ink3"], "sans", 400)
    return s


# --------------------------------------------------------------------------------------
# Benchmark: completeness by radius, with Wilson intervals and the published references
# --------------------------------------------------------------------------------------

# The benchmark on the current code (the re-run after the two fixes); the first run, on the pre-fix code, stays in
# docs/results/benchmark_real_tois.json as the historical record.
BENCH_SRC = "docs/results/benchmark_real_tois_clipfix.json"
BENCH_REFS = "docs/paper/references.json"   # the published reference values, as the methods paper's claims read them
BENCH_SAMPLE = "docs/results/benchmark_toi_sample.json"


def bench_refs() -> dict:
    """The published reference points, from the methods paper's references file (values and their stated scope)."""
    refs = load_json(BENCH_REFS)
    vals, cite = refs["values"], {k: v["cite"] for k, v in refs["refs"].items()}
    rv, hi, mid = vals["robovetter_completeness"], vals["pht_large"], vals["pht_mid"]
    p_max = re.search(r"P < (\d+) d", rv["context"])
    hi_r = re.search(r"larger than (\d+) R⊕", hi["context"])
    mid_r = re.search(r"(\d+) to (\d+) R⊕", mid["context"])
    if not (p_max and hi_r and mid_r) or hi["ref"] != mid["ref"]:
        sys.exit(f"gen_readme_assets: the reference values in {BENCH_REFS} have changed shape; update bench_refs()")

    def pct_of(v: dict) -> int:
        out = round(100 * v["value"])
        if abs(100 * v["value"] - out) > 1e-9:
            sys.exit(f"gen_readme_assets: {BENCH_REFS} value {v['value']} is not a whole percentage; update bench_refs()")
        return out

    return {"robovetter": pct_of(rv), "robovetter_p": int(p_max.group(1)), "robovetter_ref": cite[rv["ref"]],
            "pht_hi": pct_of(hi), "pht_hi_r": int(hi_r.group(1)), "pht_mid": pct_of(mid),
            "pht_mid_r": (int(mid_r.group(1)), int(mid_r.group(2))), "pht_ref": cite[mid["ref"]]}


def _rate(k: int, n: int) -> dict:
    p, lo, hi = BT.wilson(k, n)
    return {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}


def _verdict(ours: dict, ref: float) -> str:
    """Below or above only when the Wilson interval excludes the reference."""
    return "below" if ours["hi"] < ref else "above" if ours["lo"] > ref else "consistent"


def bench_data() -> dict:
    b = load_json(BENCH_SRC)
    h = b["summary"]["held_out"]
    tois = {x["toi"]: x for x in load_json(BENCH_SAMPLE)["tois"]}
    # The held-out CP/KP stars with data, from the per-star rows (as the paper's numbers script bins them).
    pos = [r for r in b["per_star"] if r.get("real") and tois[r["toi"]]["half"] == "held_out" and tois[r["toi"]]["class"] == "positive"]
    if len(pos) != h["completeness"]["n"] or sum(r["real"]["recovered"] for r in pos) != h["completeness"]["k"]:
        sys.exit("gen_readme_assets: the per-star rows disagree with the held-out completeness")

    def radius_rate(lo_r: float, hi_r: float) -> dict:
        sel = [r for r in pos if tois[r["toi"]].get("radius_re") is not None and lo_r <= tois[r["toi"]]["radius_re"] < hi_r]
        return _rate(sum(r["real"]["recovered"] for r in sel), len(sel))

    rf = bench_refs()
    lo_m, hi_m = rf["pht_mid_r"]
    cmp_ = [
        {"key": "robovetter", "bin": "All radii", "ours": h["completeness"], "ref": rf["robovetter"] / 100, "bound": True,
         "who": "Kepler Robovetter DR25", "ref_text": f"> {rf['robovetter']}%",
         "name": "the Kepler Robovetter's completeness", "note": f"vetting only, on detected TCEs, P < {rf['robovetter_p']} d"},
        {"key": "pht_mid", "bin": f"{lo_m}–{hi_m} R⊕", "ours": radius_rate(lo_m, hi_m), "ref": rf["pht_mid"] / 100, "bound": False,
         "who": "Planet Hunters TESS", "ref_text": f"{rf['pht_mid']}%",
         "name": f"Planet Hunters TESS's rate at {lo_m} to {hi_m} R⊕", "note": "a citizen-science search"},
        {"key": "pht_hi", "bin": f"> {rf['pht_hi_r']} R⊕", "ours": radius_rate(rf["pht_hi_r"], math.inf), "ref": rf["pht_hi"] / 100,
         "bound": False, "who": "Planet Hunters TESS", "ref_text": f"{rf['pht_hi']}%",
         "name": f"Planet Hunters TESS's rate above {rf['pht_hi_r']} R⊕", "note": "a citizen-science search"},
    ]
    for c in cmp_:
        c["verdict"] = _verdict(c["ours"], c["ref"])
    first = (b.get("against_first_run") or {}).get("rows", [{}])[0].get("first")
    return {"b": b, "h": h, "u": b["summary_unaffected"]["held_out"], "first": first, "refs": rf, "cmp": cmp_,
            "commit": commit_of(BENCH_SRC, BENCH_REFS, BENCH_SAMPLE)}


def first_run_text(d: dict) -> str:
    """The comparison line under the headline: the first run on the pre-fix code, or the stars the bug exposed left out."""
    if d.get("first"):
        f_ = d["first"]
        return f"first run, pre-fix code: {pct(f_['rate'])} ({f_['k']}/{f_['n']})"
    uc = d["u"]["completeness"]
    return f"without the stars exposed to the known clipping bug {pct(uc['rate'])} ({uc['k']}/{uc['n']})"


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def bench_verdict(d: dict) -> str:
    """The comparison sentence, from the intervals: below or above only when the interval excludes the reference."""
    parts = []
    for word in ("below", "above"):
        sel = [c for c in d["cmp"] if c["verdict"] == word]
        if sel:
            parts.append(f"SetuHQ is {word} {_and([c['name'] for c in sel])} ("
                         + ("the interval excludes it" if len(sel) == 1 else "each interval excludes the reference") + ")")
    for c in [c for c in d["cmp"] if c["verdict"] == "consistent"]:
        o, ref = c["ours"], c["ref"]
        diff = 100 * (o["rate"] - ref)
        where = c["name"].split("rate ", 1)[1] if "rate " in c["name"] else ""
        parts.append(f"not distinguishable from {c['who']}'s {c['ref_text']} {where} ({pct(o['rate'])}, {pct(o['lo'])}–"
                     f"{pct(o['hi'])} over {o['n']} stars; a {abs(diff):.0f}-point {'lower' if diff < 0 else 'higher'} "
                     "estimate the interval cannot resolve)")
    s = "; ".join(parts) + "."
    if any(c["who"] == "Planet Hunters TESS" for c in d["cmp"]):
        s += " Planet Hunters TESS's rates carry their own uncertainty and come from sectors 1 to 26."
    return s[0].upper() + s[1:]


def _ci_bar(s: Svg, t: dict, x, w, y_of, row: dict, color: str, on: str) -> None:
    s.rect(x, y_of(row["rate"]), w, y_of(0) - y_of(row["rate"]), fill=soft(t, color, 0.22, on), r=4)
    s.line(x, y_of(row["rate"]), x + w, y_of(row["rate"]), color, 2.4)
    cxx = x + w / 2
    s.line(cxx, y_of(row["lo"]), cxx, y_of(row["hi"]), t["ink"], 1.4)
    s.line(cxx - 7, y_of(row["lo"]), cxx + 7, y_of(row["lo"]), t["ink"], 1.4)
    s.line(cxx - 7, y_of(row["hi"]), cxx + 7, y_of(row["hi"]), t["ink"], 1.4)


def _bin_label(lo, hi, unit, last=False) -> str:
    lo_s = f"{lo:g}"
    return f"> {lo_s} {unit}" if last else f"< {hi:g} {unit}" if lo == 0 else f"{lo_s}–{hi:g} {unit}"


def _pct_ci(r: dict) -> str:
    return f"{pct(r['rate'])} ({r['k']}/{r['n']}, {pct(r['lo'])}–{pct(r['hi'])})"


def bench_desc(d: dict) -> str:
    h, u, rf, b = d["h"], d["u"], d["refs"], d["b"]
    rad = "; ".join(f"{_bin_label(*x['bin'], 'R⊕', i == len(h['completeness_by_radius']) - 1)}: {_pct_ci(x)}"
                    for i, x in enumerate(h["completeness_by_radius"]))
    per = "; ".join(f"{x['bin'][0]:g}–{x['bin'][1]:g} d: {_pct_ci(x)}" for x in h["completeness_by_period"])
    cmps = "; ".join(f"{c['bin']}: SetuHQ {_pct_ci(c['ours'])} against {c['who']} {c['ref_text']} ({c['note']})" for c in d["cmp"])
    return (f"Blind benchmark on {b['stars_run']} real TESS Objects of Interest (NASA Exoplanet Archive TOI table, fetched "
            f"{b['sample']['fetched_at'][:10]}, seed {b['sample']['seed']}), held-out half, the three Probes. Completeness is the share of "
            f"confirmed or known planets (CP/KP) on searchable stars recovered as a vetted dip on the ephemeris, with Wilson 95% intervals. "
            f"Left, in the bins the published references use: {cmps}. {bench_verdict(d)} "
            f"Right: overall {_pct_ci(h['completeness'])}; {first_run_text(d)}. By planet radius: {rad}. By period: {per}. References, each value checked in its source paper: "
            f"{rf['robovetter_ref']}; {rf['pht_ref']}. Measured on a stated benchmark, not discoveries. "
            f"Sources: {BENCH_SRC}, {BENCH_SAMPLE} (radii) and {BENCH_REFS} (references), commit {d['commit']}.")


def benchmark(t: dict, d: dict) -> Svg:
    h, u, b = d["h"], d["u"], d["b"]
    s = Svg(W, H, "Completeness on real TOIs, against the published references in matched bins", bench_desc(d))
    frame(s, t, f"Evidence · blind benchmark · {b['stars_run']} real TOIs · held-out half",
          "Completeness on real TOIs, in the references' own bins",
          f"Source: {BENCH_SRC} · {BENCH_SAMPLE} · {BENCH_REFS} (references) · commit {d['commit']}", t["known"])
    # ---- left: the three matched comparisons
    LX0, LX1 = MX0, 760
    panel(s, t, LX0, PLOT_TOP, LX1 - LX0, PLOT_BOTTOM - PLOT_TOP)
    label_tag(s, t, LX0 + 18, PLOT_TOP + 24, "Measured · Wilson 95% intervals", t["known"])
    PX0, PX1, PY0, PY1 = LX0 + 58, LX1 - 20, 150, 372
    y_of = lambda p: PY1 - p * (PY1 - PY0)  # noqa: E731
    for p in (0, 0.25, 0.5, 0.75, 1.0):
        s.line(PX0, y_of(p), PX1, y_of(p), line(t, 0 if p else 1, t["panel"]))
        s.text(pct(p), PX0 - 10, y_of(p) + 3.5, 10, t["ink3"], "mono", 400, anchor="end")
    n = len(d["cmp"])
    cw = (PX1 - PX0) / n
    ref_col = {"robovetter": t["green"], "pht_mid": t["amber"], "pht_hi": t["amber"]}
    for i, c in enumerate(d["cmp"]):
        gx = PX0 + i * cw
        bw = cw * 0.3
        xo, xr = gx + cw * 0.14, gx + cw * 0.56
        o = c["ours"]
        _ci_bar(s, t, xo, bw, y_of, o, t["known"], t["panel"])
        s.text(pct(o["rate"]), xo + 6, y_of(0) - 9, 13, t["ink"], "sans", 600)
        rc = ref_col[c["key"]]
        s.rect(xr, y_of(c["ref"]), bw, y_of(0) - y_of(c["ref"]), fill=soft(t, rc, 0.16, t["panel"]), r=4)
        s.line(xr, y_of(c["ref"]), xr + bw, y_of(c["ref"]), rc, 2.4, dash="5 3" if c["bound"] else None)
        s.text(("> " if c["bound"] else "") + pct(c["ref"]), xr + 6, y_of(0) - 9, 13, rc, "sans", 600)
        cx_ = gx + cw / 2
        s.text(c["bin"], cx_, PY1 + 20, 12.5, t["ink"], "sans", 600, anchor="middle")
        yy = PY1 + 36
        for ln in wrap(f"SetuHQ {o['k']}/{o['n']} against {c['who']}", cw - 16, 10, "mono") + wrap(c["note"], cw - 16, 10, "mono"):
            s.text(ln, cx_, yy, 10, t["ink3"], "mono", 400, anchor="middle")
            yy += 14
        word = {"below": "below: interval excludes it", "above": "above: interval excludes it",
                "consistent": "consistent: interval includes it"}[c["verdict"]]
        s.text(word, cx_, yy + 8, 11, t["rejected"] if c["verdict"] == "below" else t["ink2"], "sans", 600, anchor="middle")
    lx = LX0 + 18
    for col, lab in ((t["known"], "SetuHQ, held-out"), (t["green"], "Kepler Robovetter"), (t["amber"], "Planet Hunters TESS")):
        s.rect(lx, PLOT_BOTTOM - 24, 10, 10, fill=col, r=2)
        lx += 16 + s.text(lab, lx + 16, PLOT_BOTTOM - 15, 11, t["ink2"], "sans", 500) + 18
    s.text("dashed: a lower bound", LX1 - 18, PLOT_BOTTOM - 15, 10, t["ink3"], "mono", 400, anchor="end")
    # ---- right: the headline, by radius and by period
    RX0, RX1 = 790, MX1
    panel(s, t, RX0, PLOT_TOP, RX1 - RX0, PLOT_BOTTOM - PLOT_TOP)
    c0 = h["completeness"]
    s.text("Held-out completeness", RX0 + 20, PLOT_TOP + 28, 11, t["ink3"], "mono", 500, ls=0.08, upper=True)
    s.text(pct(c0["rate"]), RX0 + 20, PLOT_TOP + 80, 50, t["ink"], "sans", 600, ls=-0.03)
    s.text(f"{c0['k']} of {c0['n']} · interval {pct(c0['lo'])}–{pct(c0['hi'])}", RX0 + 20, PLOT_TOP + 102, 11.5, t["ink2"], "mono", 400)
    s.text(first_run_text(d) if d.get("first") else f"{pct(u['completeness']['rate'])} ({u['completeness']['k']}/{u['completeness']['n']}) "
           "without the clipping-bug stars", RX0 + 20, PLOT_TOP + 120, 11.5, t["ink3"], "mono", 400)
    QX0, QX1 = RX0 + 84, RX1 - 92
    qx = lambda p: QX0 + p * (QX1 - QX0)  # noqa: E731

    def rows(title, items, y):
        s.text(title, RX0 + 20, y, 10.5, t["ink3"], "mono", 500, ls=0.08, upper=True)
        for lab, row in items:
            y += 23
            s.text(lab, RX0 + 20, y + 4, 11.5, t["ink"], "sans", 500)
            s.line(QX0, y, QX1, y, line(t, 1, t["panel"]), 7, extra='stroke-linecap="round"')
            s.line(qx(row["lo"]), y, qx(row["hi"]), y, soft(t, t["known"], 0.45, t["panel"]), 7, extra='stroke-linecap="round"')
            s.circle(qx(row["rate"]), y, 4.5, fill=t["known"], stroke=t["panel"], sw=1.5)
            s.text(pct(row["rate"]), QX1 + 12, y + 4, 11.5, t["ink"], "mono", 500)
            s.text(f"{row['k']}/{row['n']}", RX1 - 18, y + 4, 10, t["ink3"], "mono", 400, anchor="end")
        return y

    nr = len(h["completeness_by_radius"])
    y = rows("By planet radius", [(_bin_label(*x["bin"], "R⊕", i == nr - 1), x) for i, x in enumerate(h["completeness_by_radius"])],
             PLOT_TOP + 154)
    y = rows("By orbital period", [(f"{x['bin'][0]:g}–{x['bin'][1]:g} d", x) for x in h["completeness_by_period"]], y + 34)
    for p in (0, 0.5, 1):
        s.text(pct(p), qx(p), y + 22, 10, t["ink3"], "mono", 400, anchor="middle")
    return s




# --------------------------------------------------------------------------------------
# Feed noise: false new signals per 100 targets on the controls, against the live feed
# --------------------------------------------------------------------------------------


def feed_rows(d: dict) -> list[dict]:
    f_ = d["h"]["feed"]
    imp = d["b"]["feed_implication"]
    k = BT.FEED_SECTORS_PER_TARGET * 100
    rows = []
    for key, label, sub in (("scrambled", "Control: block-scrambled light curves", "every signal destroyed"),
                            ("inverted", "Control: flux-inverted light curves", "every dip turned into a bump"),
                            ("real", "Real light curves of TOI hosts", "signals matching no published TOI")):
        r = f_[key]
        p, lo, hi = BT.wilson(r["new_signals"], r["star_sectors"])
        rows.append({"key": key, "label": label, "sub": sub, "rate": p * k, "lo": lo * k, "hi": hi * k,
                     "k": r["new_signals"], "n": r["star_sectors"], "unit": "star-sectors"})
    live = imp["live"]
    old_rule = " under the old rule" if d["b"].get("feed_rule") else ""
    rows.insert(0, {"key": "live", "label": f"Live feed{old_rule}, “new” signals", "sub": f"{Path(live['source']).name}, {live['updated'][:10]}",
                    "rate": imp["live_new_signals_per_100_targets"], "lo": imp["live_ci_per_100_targets"][0],
                    "hi": imp["live_ci_per_100_targets"][1], "k": live["new_signals"], "n": live["targets_reviewed"], "unit": "targets"})
    rows += feed_rule_rows(d["b"].get("feed_rule"))
    return rows


def feed_rule_rows(fr: dict | None) -> list[dict]:
    """The pre-registered two-sector rule's one held-out evaluation (old and new rule, discovery config, worse control)
    and the live feed re-run under it, when the benchmark JSON carries them."""
    if not fr or not fr.get("validation"):
        return []
    v = fr["validation"]
    out = []
    for key, part, label in (("rule-old", "held_out_old_rule", "Feed-rule test, old rule: worse control"),
                             ("rule-new", "held_out", "Feed-rule test, two-sector rule: worse control")):
        x = v[part]
        k = max(x["inverted"]["new_signals"], x["scrambled"]["new_signals"])
        lo, hi = x["expected_false_ci_per_100_targets"]
        out.append({"key": key, "label": label, "sub": "held-out, discovery config", "rate": x["expected_false_per_100_targets"],
                    "lo": lo, "hi": hi, "k": k, "n": x["targets"], "unit": "targets"})
    live = fr.get("live")
    if live:
        p, lo, hi = BT.wilson(live["new_signals"], live["targets"])
        out.append({"key": "rerun", "label": "Live feed re-run, two-sector rule", "sub": f"new signals, {live['when'][:10]}",
                    "rate": 100 * p, "lo": 100 * lo, "hi": 100 * hi, "k": live["new_signals"], "n": live["targets"], "unit": "targets"})
    return out


def feed_desc(d: dict) -> str:
    rows = feed_rows(d)
    imp = d["b"]["feed_implication"]
    parts = "; ".join(f"{r['label']}: {r['rate']:.1f} per 100 targets ({r['k']} over {r['n']} {r['unit']}; {r['lo']:.1f}–{r['hi']:.1f})" for r in rows)
    return ("False new signals per 100 targets: what the feed's own admission rule passes on light curves with every signal destroyed, "
            f"against the live feed. Wilson 95% intervals; a target is {BT.FEED_SECTORS_PER_TARGET} sectors. {parts}. "
            f"Expected from noise alone (the worse control): {imp['expected_false_per_100_targets']:.1f} per 100 targets, so the live feed's "
            "“new” signals were consistent with noise under the old rule. " + feed_rule_sentence(d) +
            f"Source: {BENCH_SRC} (held-out half, feed-level table{', feed_rule' if d['b'].get('feed_rule') else ''}), commit {d['commit']}.")


def fold_text(fr: dict) -> str:
    """How many times lower the worse control's noise is under the two-sector rule than under the old one."""
    o, n = fr["validation"]["held_out_old_rule"], fr["validation"]["held_out"]
    a, b = o["expected_false_per_100_targets"], n["expected_false_per_100_targets"]
    return f"{a / b:.1f}-fold" if b else "to zero"


def feed_rule_sentence(d: dict) -> str:
    fr = d["b"].get("feed_rule")
    if not fr or not fr.get("validation"):
        return "A fix is proposed in the benchmark report and not applied. "
    n = fr["validation"]["held_out"]
    where = ("measured on the held-out half with the discovery config on the current code" if fr.get("edition") == "clipfix"
             else "tested once on the held-out half with the discovery config")
    more = n["expected_false_per_100_targets"] >= n["real_new_per_100_targets"]
    return (f"The pre-registered two-sector rule (FAP < 0.001 over 2,000 trials, the signal in both sectors), {where}, lowers the worse "
            f"control {fold_text(fr)}, " + ("but noise still outnumbers the " if more else "and noise is now below the ")
            + f"{n['real_new_per_100_targets']:.1f} real new signals per 100 targets, so admissions are leads for review. ")


def feed_noise(t: dict, d: dict) -> Svg:
    rows = feed_rows(d)
    imp = d["b"]["feed_implication"]
    s = Svg(W, H, "The live feed's new signals against the controls", feed_desc(d))
    fr = d["b"].get("feed_rule")
    if fr and fr.get("validation"):
        n = fr["validation"]["held_out"]
        title = (f"Noise falls {fold_text(fr)} under the new rule, and "
                 + ("still outnumbers real signals" if n["expected_false_per_100_targets"] >= n["real_new_per_100_targets"]
                    else "falls below the real signals"))
    else:
        title = "The live feed's “new” signals are consistent with noise"
    frame(s, t, "Evidence · feed-level false alarms · held-out half", title,
          f"Source: {BENCH_SRC} (feed-level table and feed_implication) · commit {d['commit']}", t["open"])
    panel(s, t, MX0, PLOT_TOP, MX1 - MX0, PLOT_BOTTOM - PLOT_TOP)
    label_tag(s, t, MX0 + 18, PLOT_TOP + 24, "Measured · Wilson 95% intervals", t["known"])
    BX0, BX1 = 470, 1120
    vmax = max(40.0, math.ceil(max(r["hi"] for r in rows) / 10) * 10)
    bx = lambda v: BX0 + v / vmax * (BX1 - BX0)  # noqa: E731
    top, rh = 168, min(74, 296 // len(rows))
    for v in nice_ticks(0, vmax, 4):
        s.line(bx(v), top - 14, bx(v), top + rh * len(rows) - 10, line(t, 0 if v else 1, t["panel"]))
        s.text(f"{v:g}", bx(v), top + rh * len(rows) + 6, 10, t["ink3"], "mono", 400, anchor="middle")
    s.text("“New” signals per 100 targets reviewed", BX1, top + rh * len(rows) + 28, 10.5, t["ink3"], "mono", 500, anchor="end")
    col = {"live": t["open"], "scrambled": t["ink2"], "inverted": t["ink2"], "real": t["known"],
           "rule-old": t["ink2"], "rule-new": t["ink2"], "rerun": t["open"]}
    for i, r in enumerate(rows):
        yy = top + i * rh + 18
        s.text(r["label"], MX0 + 22, yy - 2, 14, t["ink"], "sans", 600 if r["key"] == "live" else 500)
        s.text(f"{r['sub']} · {r['k']} over {r['n']} {r['unit']}", MX0 + 22, yy + 16, 10.5, t["ink3"], "mono", 400)
        c_ = col[r["key"]]
        s.rect(BX0, yy - 11, bx(r["rate"]) - BX0, 22, fill=soft(t, c_, 0.25, t["panel"]), r=4)
        s.line(bx(r["rate"]), yy - 11, bx(r["rate"]), yy + 11, c_, 2.4)
        s.line(bx(r["lo"]), yy, bx(r["hi"]), yy, t["ink"], 1.4)
        for v in (r["lo"], r["hi"]):
            s.line(bx(v), yy - 6, bx(v), yy + 6, t["ink"], 1.4)
        s.text(f"{r['rate']:.1f}", bx(r["hi"]) + 10, yy + 4.5, 13, t["ink"], "mono", 600)
    s.text(f"Controls and TOI hosts: per star-sector × {BT.FEED_SECTORS_PER_TARGET} sectors per target × 100.",
           MX0 + 22, top + rh * len(rows) + 28, 10.5, t["ink3"], "mono", 400)
    ex = imp["expected_false_per_100_targets"]
    s.line(bx(ex), top - 24, bx(ex), top + rh * len(rows) - 10, t["rejected"], 1.6, dash="6 5")
    s.text(f"{'old rule, ' if d['b'].get('feed_rule') else ''}expected from noise alone: {ex:.1f}", bx(ex) + 8, top - 18, 10.5,
           t["rejected"], "mono", 500)
    return s


# --------------------------------------------------------------------------------------
# Sky coverage: a Mollweide map of TESS, Kepler, K2 and the unmapped sky
# --------------------------------------------------------------------------------------

COV_SRC = "docs/results/survey_coverage.json"


def mollweide(ra: float, dec: float, cx: float, cy: float, a: float, ra0: float = 0.0) -> tuple[float, float]:
    """Equal-area Mollweide; RA increases to the left (the sky seen from inside), centred on ra0."""
    lam = -math.radians(((ra - ra0 + 180) % 360) - 180)
    phi = math.radians(dec)
    th = phi
    for _ in range(50):
        if abs(abs(phi) - math.pi / 2) < 1e-9:
            th = phi
            break
        d_ = -(2 * th + math.sin(2 * th) - math.pi * math.sin(phi)) / (2 + 2 * math.cos(2 * th))
        th += d_
        if abs(d_) < 1e-10:
            break
    return cx + a / math.pi * lam * math.cos(th), cy - a / 2 * math.sin(th)


def cov_data() -> dict:
    c = load_json(COV_SRC)
    return {"c": c, "commit": commit_of(COV_SRC)}


def _in_corot(c, ra, dec) -> bool:
    for e in c["corot"]["eyes"]:
        cosd = (math.sin(math.radians(dec)) * math.sin(math.radians(e["dec"]))
                + math.cos(math.radians(dec)) * math.cos(math.radians(e["dec"])) * math.cos(math.radians(ra - e["ra"])))
        if math.degrees(math.acos(max(-1, min(1, cosd)))) <= c["corot"]["radius_deg"]:
            return True
    return False


def _in_bulge(c, ra, dec) -> bool:
    lon, lat = GX.galactic_lb(ra, dec)
    lon = (lon + 180) % 360 - 180
    return c["bulge"]["l"][0] <= lon <= c["bulge"]["l"][1] and c["bulge"]["b"][0] <= lat <= c["bulge"]["b"][1]


TESS_BANDS = [(1, 2), (3, 5), (6, 12), (13, 10_000)]


def cov_desc(d: dict) -> str:
    c = d["c"]
    fr, hi = c["fractions"], c["hosts_in"]
    return (f"Sky coverage on an equal-area Mollweide map in equatorial coordinates (right ascension increasing to the left: 12h at both rims, 6h, 0h at the centre, 18h; "
            f"declination ±90°, with the ±60° lines labelled), as of {c['as_of']}. TESS sectors 1 to {c['tess_last_sector']} cover {100 * fr['tess']:.1f}% of the sky, "
            f"shaded by the number of sectors (1–2, 3–5, 6–12, 13 or more; 13 or more is {100 * fr['tess_cvz_13plus']:.1f}%). "
            f"Kepler's field covers {100 * fr['kepler']:.1f}% and the K2 campaigns C0–C19 {100 * fr['k2']:.1f}%, drawn from their "
            f"CCD channel outlines; the sky in no footprint (TESS, Kepler, K2, CoRoT or the bulge), drawn as grey cells, is {100 * fr['unmapped']:.1f}%. "
            f"Of {fmt_int(hi['all'])} planet hosts, {fmt_int(hi['tess'])} lie in TESS's sky, {fmt_int(hi['kepler'])} in Kepler's field, "
            f"{fmt_int(hi['k2'])} in K2's and {fmt_int(hi['none'])} in none. The dashed line is the Galactic plane. "
            f"Source: {COV_SRC} (tess-point and K2fov footprints), commit {d['commit']}.")


def sky_coverage(t: dict, d: dict) -> Svg:
    c = d["c"]
    fr, hi = c["fractions"], c["hosts_in"]
    s = Svg(W, H, "Sky coverage: TESS, Kepler, K2 and the unmapped sky", cov_desc(d))
    frame(s, t, f"Sky · survey footprints · as of {c['as_of']}", "Where the sky has been watched",
          f"Source: {COV_SRC} (tess-point; K2fov) · commit {d['commit']}", t["sen"])
    cx, cy, a = 412, 322, 372          # semi-major axis a (px); the map is 2a x a
    panel(s, t, MX0, PLOT_TOP, 744, PLOT_BOTTOM - PLOT_TOP)
    clip = s.uid("sky")
    s.defs.append(f'<clipPath id="{clip}"><ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(a)}" ry="{f(a / 2)}"/></clipPath>')
    s.add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(a)}" ry="{f(a / 2)}" fill="{t["bg"]}"/>')
    s.ellipses.append((cx, cy, a, a / 2))
    s.add(f'<g clip-path="url(#{clip})">')
    dr = c["draw"]
    kep, k2 = set(dr["kepler"]), set(dr["k2"])
    cell_r = math.sqrt(math.pi * a * a / 2 / dr["n"] / math.pi) * 1.18
    tess_col = t["known"]
    shades = [0.28, 0.48, 0.7, 1.0]
    buckets: dict[int, list] = {i: [] for i in range(len(TESS_BANDS))}
    unmapped = []
    for i in range(dr["n"]):
        ra, dec, n_ = dr["ra"][i], dr["dec"][i], dr["tess"][i]
        p = mollweide(ra, dec, cx, cy, a)
        if n_ > 0:
            for j, (lo_, hi_) in enumerate(TESS_BANDS):
                if lo_ <= n_ <= hi_:
                    buckets[j].append(p)
        elif i not in kep and i not in k2 and not _in_corot(c, ra, dec) and not _in_bulge(c, ra, dec):
            unmapped.append(p)
    for j in range(len(TESS_BANDS)):
        s.dots(buckets[j], soft(t, tess_col, shades[j], t["bg"]), cell_r)
    unmapped_col = soft(t, t["ink"], 0.62, t["bg"])   # one solid colour, used for the cells and the legend swatch
    s.dots(unmapped, unmapped_col, cell_r)

    def quad(q, color):
        pts = [mollweide(x, y, cx, cy, a) for x, y in q]
        if max(p[0] for p in pts) - min(p[0] for p in pts) > a:  # straddles the map's edge: skip the sliver
            return
        s.poly(pts, fill=color, close=True, stroke=color, sw=0.6)

    for q in c["kepler"]["channels"]:
        quad(q, t["green"])
    for camp in c["k2"]:
        for q in camp["channels"]:
            quad(q, t["amber"])
    # graticule and the Galactic plane
    for dec in (-60, -30, 0, 30, 60):
        s.poly([mollweide(ra, dec, cx, cy, a) for ra in np.linspace(-179.999, 179.999, 121)], stroke=line(t, 2, t["bg"]), sw=0.8)
    for ra in range(-150, 181, 30):
        s.poly([mollweide(ra if ra != 180 else 179.999, dec, cx, cy, a) for dec in np.linspace(-89.9, 89.9, 91)],
               stroke=line(t, 2, t["bg"]), sw=0.8)
    gp = []
    inv = np.array(GX.ICRS_TO_GAL).T
    for lon in np.linspace(0, 360, 361):
        v = inv @ np.array([math.cos(math.radians(lon)), math.sin(math.radians(lon)), 0.0])
        gp.append((math.degrees(math.atan2(v[1], v[0])) % 360, math.degrees(math.asin(v[2]))))
    seg = []
    for ra, dec in gp:
        p = mollweide(ra, dec, cx, cy, a)
        if seg and abs(p[0] - seg[-1][0]) > a:
            s.poly(seg, stroke=t["ink2"], sw=1.1, dash="5 5")
            seg = []
        seg.append(p)
    s.poly(seg, stroke=t["ink2"], sw=1.1, dash="5 5")
    s.add("</g>")
    s.add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(a)}" ry="{f(a / 2)}" fill="none" stroke="{line(t, 2, t["bg"])}" stroke-width="1"/>')
    def plate(lab, x, y, anchor="middle", size=9.5, col=None):
        """A graticule label on a small plate of the map's ground, so it reads over any shading."""
        w_ = tw(lab, size, "mono", 500)
        x0 = x - w_ / 2 if anchor == "middle" else x - w_ if anchor == "end" else x
        s.rect(x0 - 4, y - size * 0.95, w_ + 8, size * 1.35, fill=t["bg"], r=3, extra='fill-opacity="0.82"')
        s.text(lab, x, y, size, col or t["ink2"], "mono", 500, anchor=anchor)

    for ra, lab in ((90, "6h"), (-90, "18h")):
        plate(lab, mollweide(ra, 0, cx, cy, a)[0], cy - 6)
    plate("12h", cx - a + 10, cy - 6, anchor="start")      # the rim at RA 12h, inside the map
    plate("12h", cx + a - 10, cy - 6, anchor="end")
    plate("0h", cx + 6, cy - 6, anchor="start")
    plate("+60°", cx, mollweide(0, 60, cx, cy, a)[1] - 5)
    plate("−60°", cx, mollweide(0, -60, cx, cy, a)[1] + 13)
    gx, gy = mollweide(-140, -32, cx, cy, a)
    plate("Galactic plane", gx - 6, gy, anchor="end", size=10)
    s.text("RA increases to the left · equal-area", MX0 + 20, PLOT_BOTTOM - 14, 10.5, t["ink3"], "mono", 500)
    # legend
    LX = 812
    panel(s, t, LX - 12, PLOT_TOP, MX1 - LX + 12, PLOT_BOTTOM - PLOT_TOP)
    y = PLOT_TOP + 34
    s.text(f"{100 * fr['tess']:.1f}%", LX + 8, y + 26, 34, t["ink"], "sans", 600, ls=-0.03)
    s.text(f"of the sky in TESS sectors 1–{c['tess_last_sector']}", LX + 8, y + 48, 12, t["ink2"], "sans", 500)
    y += 74
    s.text("TESS sectors", LX + 8, y, 10.5, t["ink3"], "mono", 500, ls=0.1, upper=True)
    for j, (lo_, hi_) in enumerate(TESS_BANDS):
        xx = LX + 8 + j * 82
        s.rect(xx, y + 10, 74, 14, fill=soft(t, tess_col, shades[j], t["panel"]), r=3)
        s.text(f"{lo_}–{hi_}" if hi_ < 1000 else f"{lo_}+", xx, y + 40, 10.5, t["ink2"], "mono", 400)
    y += 70
    for color, lab, val in ((t["green"], "Kepler field", f"{100 * fr['kepler']:.1f}%"),
                            (t["amber"], "K2 campaigns C0–C19", f"{100 * fr['k2']:.1f}%"),
                            (unmapped_col, "In no footprint", f"{100 * fr['unmapped']:.1f}%")):
        if color == unmapped_col:   # drawn as the map draws it: a sky cell
            s.circle(LX + 14, y - 4, cell_r, fill=color)
        else:
            s.rect(LX + 8, y - 10, 12, 12, fill=color, r=3)
        s.text(lab, LX + 28, y, 13, t["ink"], "sans", 500)
        s.text(val, MX1 - 20, y, 12.5, t["ink"], "mono", 500, anchor="end")
        y += 28
    y += 14
    s.text("Planet hosts", LX + 8, y, 10.5, t["ink3"], "mono", 500, ls=0.1, upper=True)
    y += 24
    for lab, key in (("in TESS's sky", "tess"), ("in Kepler's field", "kepler"), ("in K2's fields", "k2"), ("in no footprint", "none")):
        s.text(lab, LX + 8, y, 12, t["ink2"], "sans", 500)
        s.text(f"{fmt_int(hi[key])} of {fmt_int(hi['all'])}", MX1 - 20, y, 12, t["ink"], "mono", 400, anchor="end")
        y += 21
    return s


# --------------------------------------------------------------------------------------
# Repository counts for the diagrams
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def repo_counts() -> dict:
    src = ROOT / "src" / "setuhq"
    mods = sorted(p for p in src.glob("*.py") if p.name != "__init__.py")
    cli = re.findall(r'add_parser\("([a-z-]+)"', (src / "cli.py").read_text(encoding="utf-8"))
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts="],
                         cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", out.stdout)
    if not m:
        sys.exit("gen_readme_assets: pytest --collect-only did not report a count:\n" + out.stdout[-2000:] + out.stderr[-2000:])
    tests = int(m.group(1))
    marks = {}
    for mk in ("network", "slow"):
        o = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "-m", mk],
                           cwd=ROOT, capture_output=True, text=True).stdout
        mm = re.search(r"(\d+)/\d+ tests? collected", o) or re.search(r"(\d+) tests? collected", o)
        marks[mk] = int(mm.group(1)) if mm else 0
    lb = load_json(THRESHOLD_SWEEP)
    cat = load_json("docs/results/exoplanet_catalogue.json")
    n_cat = len(cat["planets"]) if isinstance(cat.get("planets"), list) else cat.get("counts", {}).get("rows")
    return {"modules": len(mods), "cli": cli, "tests": tests, "network": marks["network"], "slow": marks["slow"],
            "chapters": len(MX.CHAPTERS), "leaderboard_trials": len(lb["trials"]), "catalogue": n_cat}


# --------------------------------------------------------------------------------------
# Pipeline flowchart, with the stored run's counts
# --------------------------------------------------------------------------------------

FLOW_SRC = ("runs/tess-pi-men-s1", "configs/tess_pi_men_s1.toml")


def flow_data() -> dict:
    man = load_json("runs/tess-pi-men-s1/manifest.json")
    cands = load_json("runs/tess-pi-men-s1/candidates.json")
    v = load_json("docs/results/pi_men_validation.json")
    n_points = 0
    for sid in sorted({c["subject_id"] for c in cands}):
        n_points += len(load_json(f"runs/tess-pi-men-s1/subjects/{sid}.json")["time"])
    passed = [c for c in cands if c["passed"]]
    kinds = Counter(r["kind"] for r in man["reviewers"])
    fap = [c for c in passed if c.get("fap") is not None]
    trials = max(c["fap_trials"] for c in fap)
    cfg = tomllib.loads((ROOT / "configs" / "tess_pi_men_s1.toml").read_text(encoding="utf-8"))
    return {"man": man, "points": n_points, "bin_minutes": cfg["run"]["bin_minutes"], "passed": len(passed), "flagged": sum(1 for c in passed if c["flags"]),
            "rejected": len(cands) - len(passed), "epochs": v["epochs_recovered"], "predicted": v["epochs_predicted"],
            "sentinels": sum(n for k_, n in kinds.items() if k_ != "simulated"), "probes": kinds.get("simulated", 0),
            "trials": trials, "k": v["joint_fit"]["k"], "subject_days": man["subject_days"],
            "commit": commit_of(*FLOW_SRC, "docs/results/pi_men_validation.json")}


def flow_nodes(d: dict) -> list[tuple[str, str, str, str]]:
    """Each step: name, what it does, what it produced in the stored run (one sentence, wrapped when drawn), colour."""
    c = d["man"]["counts"]
    return [
        ("Ingest", "TESS · CHEOPS · CSV", f"{c['light_curves']} light curve of {fmt_int(d['points'])} points", "known"),
        ("Clean", "clip · detrend · bin", f"masked local-quadratic baseline, {d['bin_minutes']:g}-minute bins", "known"),
        ("Blind-code", f"{d['subject_days']:g}-day subjects", f"{c['subjects']} subjects, no target names", "known"),
        ("Review", "the panel marks dips", f"{d['sentinels']} Sentinels + {d['probes']} Probes; {c['classifications']} classifications", "sen"),
        ("Aggregate", "skill-weighted consensus", f"{c['consensus_events']} consensus dips", "prb"),
        ("Vet", "SNR · odd/even · secondary", f"{d['passed']} passed ({d['flagged']} flagged off-ephemeris), {d['rejected']} rejected", "open"),
        ("Fit", "limb-darkened transit", f"{d['epochs']} of {d['predicted']} epochs on the ephemeris; Rp/R★ {d['k']:.4f}", "known"),
        ("FAP", "block bootstrap", f"< 10⁻⁴ over {fmt_int(d['trials'])} trials: a bound, not a value", "known"),
        ("Write", "candidates + provenance", "CSV, JSON, SQLite, a manifest and the site", "green"),
    ]


FLOW_NODE = (200, 150, 30)   # node width, height, gap


def flow_desc(d: dict) -> str:
    steps = "; ".join(f"{i + 1}. {k} ({sub.replace(' · ', ', ')}): {detail}" for i, (k, sub, detail, _) in enumerate(flow_nodes(d)))
    return ("How a run works, with the counts of SetuHQ's stored run on pi Men (TESS sector 1): " + steps
            + ". Every step's output is kept, so a run can be re-vetted from its stored classifications without asking the reviewers again. "
            f"Sources: runs/tess-pi-men-s1 (manifest.json, candidates.json, subjects), configs/tess_pi_men_s1.toml and "
            f"docs/results/pi_men_validation.json, commit {d['commit']}.")


def flow_pipeline(t: dict, d: dict) -> Svg:
    s = Svg(W, H, "How a run works", flow_desc(d))
    frame(s, t, "How a run works · counts from the stored pi Men run", "From a public light curve to a reviewed candidate",
          f"Source: runs/tess-pi-men-s1 (manifest.json, candidates.json) · configs/tess_pi_men_s1.toml · commit {d['commit']}",
          t["known"])
    nodes = flow_nodes(d)
    nw, nh, gap = FLOW_NODE
    rows = [(nodes[:5], 132), (nodes[5:], 352)]
    pos = []
    for row, y in rows:
        n_ = len(row)
        x0 = MX0 + (MX1 - MX0 - (n_ * nw + (n_ - 1) * gap)) / 2
        for i, nd in enumerate(row):
            pos.append((x0 + i * (nw + gap), y, nd))
    for i, (x, y, (kicker, sub, detail, ck)) in enumerate(pos):
        color = t[ck]
        panel(s, t, x, y, nw, nh)
        s.rect(x, y + 16, 3, 22, fill=color, r=1.5)
        s.text(f"{i + 1:02d}", x + 16, y + 32, 11, color, "mono", 600)
        s.text(kicker, x + 42, y + 32, 16, t["ink"], "sans", 600)
        s.text(sub, x + 16, y + 58, 11.5, t["ink2"], "sans", 500)
        s.line(x + 16, y + 74, x + nw - 16, y + 74, line(t, 0, t["panel"]))
        lines = wrap(detail, nw - 32, 11.5, "mono")
        if len(lines) > 3:
            sys.exit(f"gen_readme_assets: the {kicker} node's text needs {len(lines)} lines; shorten it")
        for j, ln in enumerate(lines):
            s.text(ln, x + 16, y + 98 + j * 18, 11.5, t["ink"], "mono", 400)
    for i in range(len(pos) - 1):
        x, y, _ = pos[i]
        x2, y2, _ = pos[i + 1]
        if y2 == y:
            arrow(s, t, [(x + nw + 4, y + nh / 2), (x2 - 4, y2 + nh / 2)], t["ink3"])
        else:
            mid = (y + nh + y2) / 2
            arrow(s, t, [(x + nw / 2, y + nh + 4), (x + nw / 2, mid), (x2 + nw / 2, mid), (x2 + nw / 2, y2 - 4)], t["ink3"])
    return s


# --------------------------------------------------------------------------------------
# Architecture: data in, the engine, the panel, the surfaces, the evidence
# --------------------------------------------------------------------------------------

# The data the architecture figure quotes. Its counts of modules, CLI commands, Methods chapters and tests are read
# from the tree at generation time (and recorded in MANIFEST.json); they are not tied to a commit, so a code change
# alone does not stale the figure, while a new module, command, chapter or test does.
THRESHOLD_SWEEP = "docs/threshold_sweep.json"   # the injection threshold sweep (scripts/improve.py), not the real-TOI leaderboard
ARCH_SRC = (THRESHOLD_SWEEP, "docs/results/exoplanet_map.json", "docs/results/benchmark_real_tois.json")


def arch_data() -> dict:
    rc = repo_counts()
    b = load_json(BENCH_SRC)
    m = load_json(HERO_SRC)
    return {"rc": rc, "b": b, "m": m, "commit": commit_of(*ARCH_SRC)}


def arch_columns(d: dict) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Columns of (heading, text) items; the text is one phrase, wrapped to the card when drawn."""
    rc, b, m = d["rc"], d["b"], d["m"]
    return [
        ("Public data", "known", [("exoplanet.eu", f"{fmt_int(m['counts']['rows'])} planets, fetched {m['fetched_at'][:10]}"),
                                  ("MAST", "TESS SPOC light curves"),
                                  ("TOI table", f"{b['stars_run']} TOIs sampled with seed {b['sample']['seed']}"),
                                  ("Claret 2017", "TESS limb darkening"),
                                  ("JWST", "WASP-39 b spectrum, from Zenodo")]),
        ("Engine", "known", [(f"{rc['modules']} modules", "one Python package, src/setuhq"),
                             ("Pipeline", "preprocess, subjects, search, vet, transitfit"),
                             ("Scoring", "aggregate, calibrate, benchmark_toi"),
                             ("Pages", "report, app, galaxy, methods, mission")]),
        ("Reviewer panel", "sen", [("Sentinels", "Claude by default; other providers supported and labelled"),
                                   ("Probes", "deterministic matched-filter detectors, seeded"),
                                   ("Consensus", "skill-weighted, calibrated")]),
        ("Surfaces", "prb", [(f"CLI, {len(rc['cli'])} commands", ", ".join(rc["cli"])),
                             ("App", f"{rc['chapters']} Methods chapters; Galaxy, Catalogue, Mission Control")]),
        ("Evidence", "green", [(f"{fmt_int(rc['tests'])} tests", f"{rc['network']} need the network, {rc['slow']} are slow"),
                               ("pi Men c", "checked against Huang 2018"),
                               ("Real-TOI benchmark", f"{b['stars_run']} TOIs, with controls"),
                               ("Threshold sweep", f"{rc['leaderboard_trials']} trials, losers kept"),
                               ("Provenance", "data, config and code hashes")]),
    ]


ARCH_PROVENANCE = ("Every candidate keeps its data hash, config hash, code fingerprint and every reviewer's marks; "
                   "a run can be re-vetted without asking the reviewers again.")
ARCH_CARD = (22, 112, 330)   # gap, top, height


def arch_desc(d: dict) -> str:
    parts = [f"{title}: " + "; ".join(f"{a} ({b_})" for a, b_ in items) for title, _, items in arch_columns(d)]
    return ("SetuHQ's architecture, with counts read from the repository. " + ". ".join(parts)
            + ". " + ARCH_PROVENANCE + f" Counts read from src/setuhq, the CLI and pytest --collect-only; data from "
            f"{', '.join(ARCH_SRC)} ({THRESHOLD_SWEEP} is the threshold sweep), commit {d['commit']}.")


def architecture(t: dict, d: dict) -> Svg:
    s = Svg(W, H, "SetuHQ's architecture", arch_desc(d))
    frame(s, t, "Architecture · counts read from the repository", "One engine, one panel, every surface checked",
          f"Counts: src/setuhq, pytest --collect-only · data: {THRESHOLD_SWEEP} (threshold sweep), docs/results · commit {d['commit']}",
          t["known"])
    cols = arch_columns(d)
    n = len(cols)
    gap, top, ch_ = ARCH_CARD
    cw = (MX1 - MX0 - (n - 1) * gap) / n
    inner = cw - 32
    for i, (title, ck, items) in enumerate(cols):
        x = MX0 + i * (cw + gap)
        panel(s, t, x, top, cw, ch_)
        s.rect(x + 16, top + 18, 8, 8, fill=t[ck], r=2)
        s.text(title, x + 32, top + 26, 10.5, t["ink3"], "mono", 500, ls=0.1, upper=True)
        y = top + 52
        for a, b_ in items:
            y += 8
            s.text(a, x + 16, y, 14, t["ink"], "sans", 600)
            y += 18
            for ln in wrap(b_, inner, 11, "mono"):
                s.text(ln, x + 16, y, 11, t["ink2"], "mono", 400)
                y += 16
            y += 2
        if y > top + ch_ - 8:
            sys.exit(f"gen_readme_assets: the {title} card overflows ({y - top:.0f} of {ch_} px); shorten its items")
        if i < n - 1:
            arrow(s, t, [(x + cw + 3, top + ch_ / 2), (x + cw + gap - 3, top + ch_ / 2)], t["ink3"])
    by = top + ch_ + 18
    panel(s, t, MX0, by, MX1 - MX0, PLOT_BOTTOM - by)
    s.rect(MX0 + 16, by + 19, 8, 8, fill=t["open"], r=2)
    s.text("Provenance on every output", MX0 + 32, by + 27, 10.5, t["ink3"], "mono", 500, ls=0.1, upper=True)
    s.text(ARCH_PROVENANCE, MX0 + 16, by + 54, 13.5, t["ink"], "sans", 500)
    return s




# --------------------------------------------------------------------------------------
# Methods strip: four small multiples computed with setuhq.methods
# --------------------------------------------------------------------------------------

METHODS_SRC = ("src/setuhq/methods.py", "docs/results/methods_examples.json")


@lru_cache(maxsize=None)
def _lyot_field(rho: float, mask: float) -> float:
    return MX.lyot_pupil_field(rho, mask)


def lyot_image(u: float, mask: float, stop: float, n: int = 240) -> float:
    """methods.lyot_final_intensity, with the Lyot-plane field (which does not depend on u) computed once per node."""
    k = math.pi * u
    f_ = lambda r: _lyot_field(r, mask) * MX._j0(k * r) * r  # noqa: E731
    v = MX._simpson(f_, 0.0, min(stop, 1.0) - 1e-9, n)
    if stop > 1:
        v += MX._simpson(f_, 1.0 + 1e-9, stop, n)
    return (2 * v) ** 2


def methods_data() -> dict:
    ex = MX.load_examples(str(ROOT / "docs" / "results" / "methods_examples.json"))
    pm = ex["planets"]["pi Men c"]
    k = pm["radius"] * MX.R_JUP / (pm["star_radius"] * MX.R_SUN)
    b = pm["impact_parameter"]
    u1, u2 = MX.ld_coeffs(pm["star_teff"])
    xs = np.linspace(-1.35, 1.35, 271)
    ld = [MX.transit_flux(math.hypot(x, b), k, u1, u2) for x in xs]
    flat = [MX.transit_flux(math.hypot(x, b), k, 0.0, 0.0) for x in xs]
    hd = ex["planets"]["HD 80606 b"]
    ph = np.linspace(0, 1, 401)
    rv = [MX.rv_curve(p * hd["orbital_period"], hd["orbital_period"], hd["k"], hd["eccentricity"], hd["omega"]) for p in ph]
    u0s = (0.1, 0.3, 1.0)
    tt = np.linspace(-2.5, 2.5, 301)
    ml = {u0: [MX.paczynski(math.hypot(u0, x)) for x in tt] for u0 in u0s}
    # Lyot coronagraph: the Lyot-plane field (methods.lyot_pupil_field) once on a grid, then the image integral per u
    mask = MX.MX_LYOT_MASK
    us = np.linspace(0.04, 12, 300)
    clear = [MX.airy_intensity(u) for u in us]
    lyot = {stop: [lyot_image(u, mask, stop) for u in us] for stop in (1.5, 0.8)}
    nums = MX.coronagraph_numbers()
    for stop, want in ((1.5, nums[0]), (0.8, nums[1])):  # the memoised twin must agree with the package
        got = lyot_image(8, mask, stop)
        if abs(got - want) > 1e-6 * want:
            sys.exit(f"gen_readme_assets: lyot_image({stop}) = {got} differs from methods.coronagraph_numbers() {want}")
    return {"ex": ex, "pm": pm, "k": k, "b": b, "u1": u1, "u2": u2, "xs": xs, "ld": ld, "flat": flat,
            "depth_ld": 1 - min(ld), "depth_flat": 1 - min(flat), "hd": hd, "ph": ph, "rv": rv, "u0s": u0s, "tt": tt, "ml": ml,
            "us": us, "clear": clear, "us_l": us, "lyot": lyot, "nums": nums, "mask": mask,
            "commit": commit_of(*METHODS_SRC)}


def sci(x: float) -> str:
    return MX.sci(x)


def methods_desc(d: dict) -> str:
    pm, hd, nums = d["pm"], d["hd"], d["nums"]
    peaks = ", ".join(f"u0 = {u0:g}: peak A = {MX.paczynski(u0):.2f}" for u0 in d["u0s"])
    return ("Four methods, computed with setuhq.methods (the functions the app's Methods chapters draw with and the tests check). "
            f"1. Transit with limb darkening (transit_flux): pi Men c, k = Rp/R★ = {d['k']:.4f} from exoplanet.eu's {pm['radius']} RJ and "
            f"{pm['star_radius']} R☉ star, b = {d['b']}, quadratic limb darkening u1 = {d['u1']:.3f}, u2 = {d['u2']:.3f} (Claret 2017, "
            f"Teff {pm['star_teff']:.0f} K): depth {1e6 * d['depth_ld']:.0f} ppm, against {1e6 * d['depth_flat']:.0f} ppm for a uniform disc, "
            "plotted against the planet's position across the star in stellar radii. "
            f"2. Radial velocity (rv_curve): HD 80606 b, P = {hd['orbital_period']:.2f} d, e = {hd['eccentricity']}, ω = {hd['omega']}°, "
            f"K = {hd['k']} m/s, over one orbit. "
            f"3. Microlensing (paczynski): point-lens magnification A(u), on a log scale, against time in Einstein-crossing times for {peaks}. "
            f"4. Blocking starlight (airy_intensity, lyot_final_intensity): the star's image against separation 0 to 12 λ/D on a log scale, "
            f"for a clear pupil and a Lyot coronagraph with a {d['mask']} λ/D mask; at 8 λ/D the clear pupil leaves {sci(nums[2])} of the peak, "
            f"the Lyot stop at 150% {sci(nums[0])} and at 80% {sci(nums[1])}. Axes: relative flux against position across the star in stellar radii; radial velocity in m/s, with zero marked, against orbital phase; magnification on a log scale against time in Einstein-crossing times; intensity relative to the unblocked peak on a log scale against separation in λ/D. Models from stored values, not observations. "
            f"Sources: src/setuhq/methods.py and docs/results/methods_examples.json (exoplanet.eu, fetched {d['ex']['fetched_at'][:10]}), "
            f"commit {d['commit']}.")


def methods_strip(t: dict, d: dict) -> Svg:
    pm, hd, nums = d["pm"], d["hd"], d["nums"]
    s = Svg(W, H, "Four methods, computed", methods_desc(d))
    frame(s, t, f"Methods · {repo_counts()['chapters']} chapters · computed with setuhq.methods", "How planets are found, computed rather than drawn",
          f"Source: src/setuhq/methods.py · docs/results/methods_examples.json (exoplanet.eu, {d['ex']['fetched_at'][:10]}) · commit {d['commit']}",
          t["prb"])
    n, gap = 4, 20
    pw = (MX1 - MX0 - (n - 1) * gap) / n
    top, ph_ = PLOT_TOP, PLOT_BOTTOM - PLOT_TOP

    def axes(i, title, fn, unit):
        x = MX0 + i * (pw + gap)
        panel(s, t, x, top, pw, ph_)
        s.text(f"{i + 1:02d}", x + 16, top + 30, 11, t["prb"], "mono", 600)
        s.text(title, x + 42, top + 30, 15, t["ink"], "sans", 600)
        s.text(fn, x + 16, top + 48, 10.5, t["ink3"], "mono", 400)
        s.text("y: " + unit, x + 22, top + 67, 9.5, t["ink2"], "mono", 500)
        return x, (x + 22, x + pw - 16, top + 74, top + 270)

    def plot_line(box, xs, ys, xr, yr, color, sw=2.0, dash=None, logy=False):
        X0, X1, Y0, Y1 = box
        pts = []
        for a, b_ in zip(xs, ys):
            yv = math.log10(max(b_, 1e-12)) if logy else b_
            pts.append((X0 + (a - xr[0]) / (xr[1] - xr[0]) * (X1 - X0),
                        Y1 - (min(max(yv, yr[0]), yr[1]) - yr[0]) / (yr[1] - yr[0]) * (Y1 - Y0)))
        s.poly(pts, stroke=color, sw=sw, dash=dash)

    def frame_box(box):
        X0, X1, Y0, Y1 = box
        s.rect(X0, Y0, X1 - X0, Y1 - Y0, fill=t["bg"], stroke=line(t, 0, t["bg"]), r=6)

    def captions(x, rows):
        y = top + 300
        for row in rows:
            lab, val = row[0], row[1]
            if len(row) > 2:
                s.rect(x + 16, y - 7, 10, 3, fill=row[2], r=1.5)
            s.text(lab, x + 16 + (16 if len(row) > 2 else 0), y, 10.5, t["ink3"], "mono", 500)
            s.text(val, x + pw - 16, y, 11.5, t["ink"], "mono", 500, anchor="end")
            y += 22

    # 1 transit
    x, box = axes(0, "Transit", "transit_flux · limb darkening", "relative flux")
    frame_box(box)
    lo = 1 - 1.25 * d["depth_ld"]
    plot_line(box, d["xs"], d["flat"], (-1.35, 1.35), (lo, 1 + 0.15 * d["depth_ld"]), t["ink3"], 1.4, dash="4 4")
    plot_line(box, d["xs"], d["ld"], (-1.35, 1.35), (lo, 1 + 0.15 * d["depth_ld"]), t["known"], 2.2)
    s.text("x: position across the star, R★", box[0], box[3] + 15, 9.5, t["ink3"], "mono", 400)
    captions(x, [("pi Men c, Rp/R★", f"{d['k']:.4f}"), ("impact parameter b", f"{d['b']}"),
                 ("u1, u2 (Claret 2017)", f"{d['u1']:.3f}, {d['u2']:.3f}"), ("depth, limb-darkened", f"{1e6 * d['depth_ld']:.0f} ppm"),
                 ("depth, uniform disc", f"{1e6 * d['depth_flat']:.0f} ppm")])
    # 2 RV
    x, box = axes(1, "Radial velocity", "rv_curve · Kepler's equation", "velocity, m/s (0 marked)")
    frame_box(box)
    kmax = hd["k"] * 1.25
    X0, X1, Y0, Y1 = box
    s.line(X0, (Y0 + Y1) / 2, X1, (Y0 + Y1) / 2, line(t, 1, t["bg"]))
    plot_line(box, d["ph"], d["rv"], (0, 1), (-kmax * 1.35, kmax * 0.6), t["coral"] if t["name"] == "dark" else t["rejected"], 2.2)
    s.text("x: one orbit, phase", box[0], box[3] + 15, 9.5, t["ink3"], "mono", 400)
    captions(x, [("HD 80606 b, period", f"{hd['orbital_period']:.2f} d"), ("eccentricity e", f"{hd['eccentricity']}"),
                 ("periastron argument", f"{hd['omega']}°"), ("semi-amplitude K", f"{hd['k']} m/s"), ("source", "exoplanet.eu")])
    # 3 microlensing
    x, box = axes(2, "Microlensing", "paczynski · A(u)", "magnification A, log")
    frame_box(box)
    shades = [t["prb"], soft(t, t["prb"], 0.7, t["bg"]), soft(t, t["prb"], 0.45, t["bg"])]
    for j, u0 in enumerate(d["u0s"]):
        plot_line(box, d["tt"], [math.log10(a_) for a_ in d["ml"][u0]], (-2.5, 2.5), (-0.05, 1.15), shades[j], 2.0)
    s.text("x: time, Einstein crossings", box[0], box[3] + 15, 9.5, t["ink3"], "mono", 400)
    captions(x, [(f"peak A, u0 = {u0:g}", f"{MX.paczynski(u0):.2f}", shades[j]) for j, u0 in enumerate(d["u0s"])]
             + [("lens", "a point mass"), ("source", "closed form")])
    # 4 coronagraph
    x, box = axes(3, "Blocking starlight", "airy · lyot_final_intensity", "intensity / peak, log")
    frame_box(box)
    yr = (-9.0, 0.0)
    plot_line(box, d["us"], d["clear"], (0, 12), yr, t["ink3"], 1.4, logy=True)
    plot_line(box, d["us_l"], d["lyot"][1.5], (0, 12), yr, t["amber"], 1.8, logy=True)
    plot_line(box, d["us_l"], d["lyot"][0.8], (0, 12), yr, t["green"], 2.2, logy=True)
    X0, X1, Y0, Y1 = box
    x8 = X0 + 8 / 12 * (X1 - X0)
    s.line(x8, Y0 + 4, x8, Y1 - 4, line(t, 2, t["bg"]), 1, dash="3 3")
    s.text("x: separation, λ/D", box[0], box[3] + 15, 9.5, t["ink3"], "mono", 400)
    captions(x, [("8 λ/D, clear pupil", sci(nums[2]), t["ink3"]), ("Lyot stop 150%", sci(nums[0]), t["amber"]),
                 ("Lyot stop 80%", sci(nums[1]), t["green"]),
                 ("focal mask", f"{d['mask']} λ/D"), ("optics", "Fraunhofer")])
    for i in range(4):
        label_tag(s, t, MX0 + i * (pw + gap) + 16, PLOT_BOTTOM - 14, "Model · stored values", t["prb"])
    return s


# --------------------------------------------------------------------------------------
# Build, manifest and checks
# --------------------------------------------------------------------------------------

# The figures, in README order: name -> (builder, data loader, source paths for the manifest)
FIGURES = {
    "hero": (hero, hero_data, [HERO_SRC]),
    "pi-men": (pimen, pimen_data, list(PIMEN_SRC)),
    "benchmark": (benchmark, bench_data, [BENCH_SRC, BENCH_REFS, BENCH_SAMPLE]),
    "feed-noise": (feed_noise, bench_data, [BENCH_SRC]),
    "sky-coverage": (sky_coverage, cov_data, [COV_SRC]),
    "flow-pipeline": (flow_pipeline, flow_data, list(FLOW_SRC) + ["docs/results/pi_men_validation.json"]),
    "architecture": (architecture, arch_data, list(ARCH_SRC)),
    "methods-strip": (methods_strip, methods_data, list(METHODS_SRC)),
}


def _hash_paths(paths) -> dict[str, str]:
    out = {}
    for p in paths:
        q = ROOT / p
        files = sorted(x for x in q.rglob("*") if x.is_file() and "__pycache__" not in x.parts) if q.is_dir() else [q]
        h = hashlib.sha256()
        for x in files:
            h.update(x.relative_to(ROOT).as_posix().encode() + b"\0" + x.read_bytes())
        out[p] = h.hexdigest()
    return out


def build() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    manifest: dict = {"generator": "tools/gen_readme_assets.py", "grid": {"width": W, "height": H, "margin": MX0},
                      "fonts": sorted(FONT_FILES.values()), "assets": {}}

    def put(name, fn, sources, commit):
        for t in THEMES:
            out[f"{REL_OUT}/{name}-{t['name']}.svg"] = fn(t).render().encode()
        manifest["assets"][name] = {"files": [f"{name}-{t['name']}.svg" for t in THEMES], "sources": _hash_paths(sources),
                                    "commit": commit}

    brand = brand_assets()
    out.update(brand)
    manifest["brand"] = {"files": sorted(Path(k).name for k in brand),
                         "sources": _hash_paths(["docs/assets/readme/brand/setu-mark.svg", "tools/readme-fonts/Unbounded-latin-wght.ttf"]),
                         "q": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in q_geometry().items() if k in ("r", "stroke", "advance")}}
    cache: dict = {}
    for name, (fn, loader, sources) in FIGURES.items():
        if loader not in cache:
            cache[loader] = loader()
        data = cache[loader]
        put(name, lambda t, fn=fn, data=data: fn(t, data), sources, data["commit"])
    rc = repo_counts()
    manifest["repo_counts"] = {k: v for k, v in rc.items() if k != "cli"} | {"cli_commands": rc["cli"]}
    shots = APP_DIR / "SHOTS.json"
    if shots.exists():
        manifest["app_screenshots"] = {"captured_by": "tools/capture_site_shots.mjs", "record": "app/SHOTS.json",
                                       "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(APP_DIR.glob("*.webp"))}}
    manifest["made_with"] = made_with()   # recorded, not compared: --check names them when a file differs
    out[f"{REL_OUT}/MANIFEST.json"] = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    return out


# --------------------------------------------------------------------------------------
# The README's generated parts: alt text, badges and the blocks of numbers
# --------------------------------------------------------------------------------------

GEN_BLOCK = re.compile(r"(<!-- generated:([a-z-]+) [^\n]*?-->\n)(.*?)(\n<!-- /generated:\2 -->)", re.S)
README_BLOCKS = ("badges", "pimen-results", "sentinel-results", "benchmark-results", "limits-completeness", "methods-chapters")


def _shield_part(s_: str) -> str:
    from urllib.parse import quote
    return quote(s_.replace("-", "--").replace("_", "__"), safe="")


def shield(href: str, label: str, message: str, color: str, alt: str) -> str:
    url = f"https://img.shields.io/badge/{_shield_part(label)}-{_shield_part(message)}-{color}?style=flat-square&labelColor=0A1226"
    return f'  <a href="{href}"><img src="{url}" height="18" alt="{esc(alt)}"></a>'


def badges_block() -> str:
    rc = repo_counts()
    b = load_json(BENCH_SRC)
    c = b["summary"]["held_out"]["completeness"]
    m = load_json(HERO_SRC)
    offline = rc["tests"] - rc["network"] - rc["slow"]
    rows = [
        shield("scripts/ci_local.sh", "tests", f"{rc['tests']} collected", "377D0C",
               f"{rc['tests']} tests collected by pytest: {offline} run offline in CI, {rc['slow']} slow ones and "
               f"{rc['network']} network ones by scripts/ci_local.sh"),
        shield("#evidence", "held-out completeness", f"{pct(c['rate'])} ({c['k']}/{c['n']})", "066A86",
               f"Held-out completeness on {b['stars_run']} real TOIs: {c['k']} of {c['n']} confirmed or known planets on "
               f"searchable stars, Wilson 95% interval {100 * c['lo']:.0f} to {100 * c['hi']:.0f}%"),
        shield("#the-app", "catalogue", f"{fmt_int(m['counts']['rows'])} planets", "066A86",
               f"The catalogue holds all {fmt_int(m['counts']['rows'])} {m['source_short']} records, fetched {m['fetched_at'][:10]}"),
        shield("#the-app", "Methods", f"{len(MX.CHAPTERS)} chapters", "066A86",
               f"{len(MX.CHAPTERS)} animated Methods chapters with tested physics"),
        shield("#licence", "licence", "AGPL-3.0", "3F4B67",
               "Licence: AGPL-3.0-only, or a commercial licence from Ashforde OÜ; data, benchmark and paper under CC BY 4.0"),
        shield("#editions", "commercial", "available", "B8288F",
               "A commercial licence and SetuHQ Pro are available on request from Ashforde OÜ"),
    ]
    return '<p align="center">\n' + "\n".join(rows) + "\n</p>"


def _ordinal(i: int) -> str:
    return ["first", "second", "third", "fourth", "fifth"][i] if i < 5 else f"{i + 1}th"


def _sci_label(label: str) -> str:
    """'< 1.0e-04 (...)' -> '10⁻⁴' (the bound's exponent, as the README prints it)."""
    m = re.search(r"e(-?\d+)", label)
    if not m:
        sys.exit(f"gen_readme_assets: cannot read a bound from {label!r}")
    return "10" + sup_exp(int(m.group(1)))


def pimen_results_block() -> str:
    d = pimen_data()
    v, jf, jp = d["v"], d["jf"], d["v"]["joint_fit_density_prior"]
    h = v["huang_2018"]
    r = v["ratios_vs_huang_2018"]
    ev = d["events"]
    passed = [e for e in ev if e["status"] != "rejected"]
    flagged = [e for e in passed if e["flags"]]
    rejected = [e for e in ev if e["status"] == "rejected"]
    known = [e for e in ev if e["status"] == "known"]
    xm = load_json("docs/results/pi_men_crossmatch.json")["validation"]
    span = d["t"][-1] - d["t"][0]
    star = v["star"]
    huang_t23 = TF.t23(h["pl_trandur"] / 24, h["pl_imppar"], h["pl_ratror"], h["pl_orbper"]) / (h["pl_trandur"] / 24)
    rho_in = jf["rho_range"][0] <= star["rho"] <= jf["rho_range"][1]
    fap = [c for c in d["cands"] if c["passed"] and c.get("fap") is not None]
    trials = {c["fap_trials"] for c in fap}
    if len(trials) != 1 or any(abs(c["fap"] - 1 / (c["fap_trials"] + 1)) > 1e-12 for c in fap):
        sys.exit("gen_readme_assets: the pi Men FAPs are no longer all at the trial bound; reword pimen_results_block()")
    n_trials = trials.pop()
    fap_subjects = sorted({c["subject_id"] for c in fap})
    bound, tail = _sci_label(fap[0]["fap_label"]), _sci_label(fap[0]["fap_tail_label"])
    lines = [
        f"Real data, TESS SPOC sector 1 of pi Men (TIC {star['tic']}), the three Probes plus the two Sentinels "
        "(Skeptic and Volunteer, on Claude via the CLI), as stored in `runs/tess-pi-men-s1`, run on the current code"
        + (" (the Sentinels' stored answers reused: the subject images and prompts are byte-identical)"
           if (d.get("manifest") or {}).get("sentinel_answers") else "") + ":",
        "",
        f"* {len(ev)} consensus dips: {len(passed)} passed vetting, {len(flagged)} of them flagged `off_ephemeris`, and "
        f"{len(rejected)} failed it (" + "; ".join(", ".join(f"`{x}`" for x in e["flags"]) for e in rejected) + ").",
        f"* {len(known)} of them lie on the published pi Men c ephemeris. {v['epochs_recovered']} of the {v['epochs_predicted']} "
        f"predicted epochs in the {span:.0f}-day window are recovered, with a mean timing offset of "
        + f"{xm['mean_timing_offset_min']:+.0f}".replace("-", "−")
        + " minutes against the NASA Exoplanet Archive value (docs/results/pi_men_crossmatch.json).",
        "* **Transit shape, limb-darkened fit** (see",
        "  [docs/results/pi_men_validation.md](docs/results/pi_men_validation.md)). A joint fit of",
        f"  the {jf['n_epochs']} epochs, with the period free near the BLS period ({jf['period_days']:.4f} ± {jf['period_err']:.4f} d; "
        f"Huang: {h['pl_orbper']:.5f} d), gives the like-for-like quantities first: **Rp/R★ = {jf['k']:.4f} ± {jf['k_err']:.4f} "
        f"({r['k']:.2f} against Huang et al. 2018) and T14 = {jf['t14_hours']:.2f} ± {jf['t14_err_hours']:.2f} h ({r['duration']:.2f})**. "
        f"The mid-transit depth of the limb-darkened model is {jf['depth_ppm']:.0f} ± {jf['depth_err_ppm']:.0f} ppm ({r['depth']:.2f} "
        f"against Huang's published {h['pl_trandep'] * 1e4:.0f} ppm, which is defined by that paper, not by this model). The box "
        f"measure it replaces gave {r['box_depth']:.2f} in depth and {r['box_duration']:.2f} in duration. Errors are conservative: "
        "the covariance plus the spread along the impact-parameter profile.",
        f"* **The impact parameter needs the star.** Free, {jf['n_epochs']} TESS transits give only b < {jf['b_range'][1]:.2f} (1σ), "
        f"so a/R★ and ρ★ are ranges (ρ★ {jf['rho_range'][0]:.2f} to {jf['rho_range'][1]:.1f} g/cm³ at 1σ, "
        f"{'consistent with' if rho_in else 'against'} the TIC's {star['rho']:.2f}). With the TIC density as a Gaussian prior "
        f"({star['rho']:.2f} ± {star['rho_err']:.2f} g/cm³), the fit gives b = {jp['b']:.2f} ± {jp['b_err']:.2f}, "
        f"a/R★ = {jp['a_rs']:.2f} (1σ {jp['a_rs_range'][0]:.1f} to {jp['a_rs_range'][1]:.1f}) and T23/T14 = {jp['t23_over_t14']:.2f}, "
        f"against Huang's {h['pl_imppar']}, {h['pl_ratdor']} and {huang_t23:.2f}. The fit is "
        + ("V-shaped." if jf["v_shape"] else "U-shaped, not V-shaped."),
        f"* The periodic signal's false-alarm probability is below {bound} in "
        + ("both subjects" if len(fap_subjects) == 2 else f"{len(fap_subjects)} subjects")
        + f". No one of {fmt_int(n_trials)} block-bootstrap trials reached the observed SNR, so {bound} is a bound, not a value. The "
        f"null maxima are committed in `runs/tess-pi-men-s1/fap_null/`; a Gumbel fit to them, stored as `fap_tail`, puts the tail "
        f"below {tail} (indicative only, see below).",
    ]
    for e in flagged:
        lines.append(f"* The passed dip at BTJD {e['t']:.1f} ({e['dur']:.2f} h, SNR {e['snr']:.1f}) does not fit the ephemeris and is "
                     "a likely false positive. It is kept and flagged, not hidden.")
    for e in rejected:
        lines.append(f"* The dip at BTJD {e['t']:.1f} (SNR {e['snr']:.1f}) failed vetting and stays in the stored candidates with "
                     "its flags.")
    return "\n".join(lines)


def sentinel_results_block() -> str:
    d = pimen_data()
    names = {rid: lab for rid, lab, kind in REVIEWER_ORDER if kind == "sen"}
    status = {"known": "on the ephemeris", "open": "passed but off the ephemeris", "rejected": "rejected by vetting"}
    lines = ["**What the Sentinels did in this run, read from the stored classifications:**", ""]
    for i, sub in enumerate(d["subs"]):
        evs = [e for e in d["events"] if sub["start"] <= e["t"] <= sub["end"]]
        said, marked_by_any = [], set()
        for rid in names:
            row = d["sentinel_rows"].get((rid, sub["subject_id"]))
            if row is None:
                said.append(f"{names[rid]} did not review it")
                continue
            hits = [e for e in evs if any(a - 0.1 <= e["t"] <= b + 0.1 for a, b in row["spans"])]
            marked_by_any |= {e["t"] for e in hits}
            what = ("marked the dips at " + _and([f"{e['t']:.2f}" for e in hits])) if hits else "marked none of the consensus dips"
            said.append(f"{names[rid]} {what} and labelled the subject `{row['label']}` (confidence {row['confidence']:g})")
        missed = [e for e in evs if e["t"] not in marked_by_any]
        tail = ""
        if missed:
            tail = (". Neither marked " + _and([f"the dip at {e['t']:.2f} ({status[e['status']]})" for e in missed]).replace(" and the dip", " or the dip"))
        lines.append(f"* On the {_ordinal(i)} subject (BTJD {sub['start']:.1f} to {sub['end']:.1f}), " + "; ".join(said) + tail + ".")
    w = d["weights"]
    sen_w = sorted({w[r] for r in names})
    prb_w = sorted(w[r] for r, _, k in REVIEWER_ORDER if k == "prb")
    lines.append(f"* In the consensus each Sentinel carries weight {', '.join(f'{x:g}' for x in sen_w)}, against "
                 f"{prb_w[0]:g} to {prb_w[-1]:g} for the Probes: the Sentinels are voices in a calibrated panel, not the whole panel.")
    return "\n".join(lines)


def benchmark_results_block() -> str:
    d = bench_data()
    h = d["h"]
    c = h["completeness"]
    bins = h["completeness_by_radius"]
    words = []
    for i, x in reversed(list(enumerate(bins))):
        lo, hi = x["bin"]
        where = f"above {lo:g} R⊕" if i == len(bins) - 1 else f"below {hi:g} R⊕" if lo == 0 else f"at {lo:g} to {hi:g} R⊕"
        words.append(f"{pct(x['rate'])} {where}")
    cmps = []
    for x in d["cmp"]:
        o = x["ours"]
        cmps.append(f"{x['bin'].replace('–', ' to ').replace('> ', 'above ').replace('All radii', 'all radii')}: {pct(o['rate'])} ({o['k']}/{o['n']}; {100 * o['lo']:.0f} to {100 * o['hi']:.0f}%) "
                    f"against {x['who']}'s {x['ref_text']} ({x['note']})")
    return (f"* **Completeness: {pct(c['rate'])} ({c['k']} of {c['n']} CP/KP on searchable stars; {100 * c['lo']:.0f} to "
            f"{100 * c['hi']:.0f}%).** It is {_and(words)}. In the bins the published references use: " + "; ".join(cmps)
            + f". {bench_verdict(d)}")


def limits_completeness_block() -> str:
    d = bench_data()
    h = d["h"]
    c = h["completeness"]
    small = h["completeness_by_radius"][0]
    below = [x for x in d["cmp"] if x["verdict"] == "below"]
    return (f"* **Real-TOI completeness is {pct(c['rate'])} on searchable stars** (held-out; {100 * c['lo']:.0f} to "
            f"{100 * c['hi']:.0f}%), below " + _and([x["name"] for x in below])
            + f", and only {pct(small['rate'])} for planets below {small['bin'][1]:g} R⊕. The FP measures cover only FP stars with "
            "2-minute data, a population skewed away from the full FP list.")


def methods_chapters_block() -> str:
    return (f"**Methods: {len(MX.CHAPTERS)} chapters.** " + ", ".join(title for _, title in MX.CHAPTERS)
            + ". Physics checked by tests against closed forms and published values.")


def readme_blocks() -> dict[str, str]:
    return {"badges": badges_block(), "pimen-results": pimen_results_block(), "sentinel-results": sentinel_results_block(),
            "benchmark-results": benchmark_results_block(), "limits-completeness": limits_completeness_block(),
            "methods-chapters": methods_chapters_block()}


def alt_for(path: str, assets: dict[str, bytes] | None) -> str | None:
    if path.startswith(REL_OUT + "/app/"):
        rec = json.loads((APP_DIR / "SHOTS.json").read_text(encoding="utf-8"))
        return {s_["file"]: s_["alt"] for s_ in rec["shots"]}.get(Path(path).name)
    src = assets.get(path) if assets is not None else None
    if src is None and (ROOT / path).exists():
        src = (ROOT / path).read_bytes()
    if src is None:
        return None
    return html.unescape(svg_desc(src))


def render_readme(text: str, assets: dict[str, bytes] | None = None) -> str:
    """The README as --write-readme writes it: every generated block filled, every picture's alt set from its source."""
    blocks = readme_blocks()
    seen = set()

    def fill(m):
        name = m.group(2)
        if name not in blocks:
            sys.exit(f"gen_readme_assets: README has an unknown generated block {name!r}")
        seen.add(name)
        return m.group(1) + blocks[name] + m.group(4)

    text = GEN_BLOCK.sub(fill, text)
    missing = set(README_BLOCKS) - seen
    if missing:
        sys.exit(f"gen_readme_assets: README lacks the generated blocks {sorted(missing)}")

    def pic(m):
        blk = m.group(0)
        src = re.search(r'<img src="([^"]+)"', blk)
        alt = alt_for(src.group(1), assets) if src else None
        if alt is None:
            return blk
        return re.sub(r'(<img src="[^"]+" alt=")[^"]*(")', lambda mm: mm.group(1) + esc(alt) + mm.group(2), blk)

    return re.sub(r"<picture>.*?</picture>", pic, text, flags=re.S)


def made_with() -> dict:
    import PIL
    import fontTools

    return {"python": ".".join(map(str, sys.version_info[:2])), "fonttools": fontTools.version, "numpy": np.__version__,
            "pillow": PIL.__version__}


def svg_desc(svg: bytes | str) -> str:
    txt = svg.decode() if isinstance(svg, bytes) else svg
    m = re.search(r'<desc id="d">(.*?)</desc>', txt, re.S)
    return m.group(1) if m else ""


def readme_pictures(text: str) -> list[dict]:
    """Every <picture> in the README: its dark and light sources, and the <img> src and alt."""
    out = []
    for m in re.finditer(r"<picture>(.*?)</picture>", text, re.S):
        blk = m.group(1)
        dark = re.search(r'media="\(prefers-color-scheme: dark\)" srcset="([^"]+)"', blk)
        light = re.search(r'media="\(prefers-color-scheme: light\)" srcset="([^"]+)"', blk)
        img = re.search(r'<img src="([^"]+)" alt="([^"]*)"', blk)
        out.append({"dark": dark and dark.group(1), "light": light and light.group(1), "src": img and img.group(1),
                    "alt": img and img.group(2)})
    return out


def check_readme(assets: dict[str, bytes] | None = None) -> list[str]:
    """Problems with how the README uses the figures and screenshots (also run by the tests)."""
    bad = []
    text = README.read_text(encoding="utf-8")
    pics = readme_pictures(text)
    shots = json.loads((APP_DIR / "SHOTS.json").read_text(encoding="utf-8")) if (APP_DIR / "SHOTS.json").exists() else {"shots": []}
    shot_alt = {s_["file"]: s_["alt"] for s_ in shots["shots"]}
    stray = re.findall(r'<img src="(docs/assets/(?:readme|brand)/[^"]+)"', re.sub(r"<picture>.*?</picture>", "", text, flags=re.S))
    for src in stray:
        bad.append(f"README: {src} is not inside a <picture> with light and dark sources")
    for p in pics:
        if not (p["dark"] and p["light"] and p["src"]):
            bad.append(f"README: a <picture> lacks a light or dark source or an <img>: {p}")
            continue
        if p["src"] != p["light"] or p["dark"] != p["light"].replace("-light.", "-dark."):
            bad.append(f"README: {p['src']} is not paired as -light / -dark")
        name = Path(p["light"]).name
        if p["light"].startswith(REL_OUT + "/app/"):
            for v in (p["light"], p["dark"]):
                if Path(v).name not in shot_alt:
                    bad.append(f"README: {v} is not recorded in app/SHOTS.json")
            if shot_alt.get(name) is not None and esc(shot_alt[name]) != p["alt"]:
                bad.append(f"README: the alt text of {name} is not its SHOTS.json alt")
        elif p["light"].startswith(("docs/assets/readme/", "docs/assets/brand/")):
            src = assets.get(p["light"]) if assets is not None else (ROOT / p["light"]).read_bytes() if (ROOT / p["light"]).exists() else None
            if src is None:
                bad.append(f"README: {p['light']} is not a generated figure")
                continue
            if esc(svg_desc(src).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')) != p["alt"]:
                bad.append(f"README: the alt text of {name} is not the figure's own <desc>")
        for v in (p["light"], p["dark"]):
            if not (ROOT / v).exists():
                bad.append(f"README: {v} does not exist")
    used = {Path(p["light"]).name.rsplit("-light.", 1)[0] for p in pics if p["light"]}
    for name in FIGURES:
        if name not in used:
            bad.append(f"README: the figure {name} is generated but not shown")
    return bad


SOCIAL_PNG = "docs/assets/brand/setuhq-social-card.png"   # rasterised from the SVG by capture_site_shots.mjs


def check_social_card(rec: dict, assets: dict[str, bytes] | None = None) -> list[str]:
    """The social card's PNG is recorded in SHOTS.json, unchanged, and was drawn from the current SVG."""
    card = rec.get("social_card")
    png = ROOT / SOCIAL_PNG
    if not card:
        return [f"{SOCIAL_PNG} is not recorded in app/SHOTS.json"] if png.exists() else []
    if not png.exists():
        return [f"app/SHOTS.json records {SOCIAL_PNG}, which is missing"]
    bad = []
    if hashlib.sha256(png.read_bytes()).hexdigest() != card["sha256"]:
        bad.append(f"{SOCIAL_PNG} differs from its SHOTS.json hash")
    svg = (assets or {}).get(card["source"]) or ((ROOT / card["source"]).read_bytes() if (ROOT / card["source"]).exists() else b"")
    if hashlib.sha256(svg).hexdigest() != card["source_sha256"]:
        bad.append(f"{SOCIAL_PNG} was drawn from an older {card['source']}: run tools/capture_site_shots.mjs, then --import-shots")
    return bad


def check_shots(assets: dict[str, bytes] | None = None) -> list[str]:
    bad = []
    rec_path = APP_DIR / "SHOTS.json"
    if not rec_path.exists():
        return ["app/SHOTS.json is missing"]
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    bad += check_social_card(rec, assets)
    files = {p.name for p in APP_DIR.iterdir() if p.is_file() and p.name != "SHOTS.json"}
    recorded = {s_["file"]: s_ for s_ in rec["shots"]}
    for name in sorted(files - set(recorded)):
        bad.append(f"app/{name} is not recorded in SHOTS.json")
    for name, s_ in recorded.items():
        p = APP_DIR / name
        if not p.exists():
            bad.append(f"app/SHOTS.json records {name}, which is missing")
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != s_["sha256"]:
            bad.append(f"app/{name} differs from its SHOTS.json hash")
        for k in ("route", "viewport", "device_scale_factor", "theme", "commit", "crop_css_px", "alt"):
            if k not in s_:
                bad.append(f"app/SHOTS.json: {name} lacks {k}")
    views = {}
    for s_ in rec["shots"]:
        views.setdefault(s_["view"], set()).add(s_["theme"])
    for v, th in views.items():
        if th != {"light", "dark"}:
            bad.append(f"app/SHOTS.json: the view {v} lacks a theme ({sorted(th)})")
    sizes = {(s_["width"], s_["height"]) for s_ in rec["shots"]}
    if len(sizes) > 1:
        bad.append(f"app/SHOTS.json: the screenshots are not all one size: {sorted(sizes)}")
    return bad


# --------------------------------------------------------------------------------------
# Screenshot import (from a tools/capture_site_shots.mjs run)
# --------------------------------------------------------------------------------------


def import_shots(src_dir: Path) -> None:
    from PIL import Image

    rec = json.loads((src_dir / "shots.json").read_text(encoding="utf-8"))
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for p in APP_DIR.iterdir():
        if p.is_file():
            p.unlink()
    shots = []
    for r in rec["shots"]:
        img = Image.open(src_dir / r["file"]).convert("RGB")
        h_ = round(img.height * SHOT_WIDTH / img.width)
        img = img.resize((SHOT_WIDTH, h_), Image.LANCZOS)
        name = Path(r["file"]).with_suffix(".webp").name
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=SHOT_QUALITY, method=6)
        (APP_DIR / name).write_bytes(buf.getvalue())
        shots.append({"file": name, "view": r["view"], "route": r["route"], "frame": r["frame"], "theme": r["theme"],
                      "viewport": r["viewport"], "device_scale_factor": r["device_scale_factor"], "reduced_motion": r["reduced_motion"],
                      "crop_css_px": r["crop_css_px"], "width": SHOT_WIDTH, "height": h_, "format": f"WebP, quality {SHOT_QUALITY}",
                      "commit": rec["commit"], "app_sha256": rec["app_sha256"], "captured": rec["captured"],
                      "alt": r["alt"], "sha256": hashlib.sha256(buf.getvalue()).hexdigest()})
        print(f"{len(buf.getvalue()):>9,}  {APP_DIR / name}")
    doc = {"tool": "tools/capture_site_shots.mjs, imported by tools/gen_readme_assets.py --import-shots",
           "note": rec["note"], "rule": rec["rule"], "shots": shots}
    card = rec.get("social_card")
    if card:
        data = (src_dir / card["file"]).read_bytes()
        (ROOT / SOCIAL_PNG).write_bytes(data)
        doc["social_card"] = {"file": SOCIAL_PNG, "source": card["source"], "source_sha256": card["source_sha256"],
                              "width": card["width"], "height": card["height"], "commit": rec["commit"],
                              "captured": rec["captured"], "sha256": hashlib.sha256(data).hexdigest(),
                              "rasterised_by": "Chromium (tools/capture_site_shots.mjs), the SVG at its own size"}
        print(f"{len(data):>9,}  {ROOT / SOCIAL_PNG}")
    (APP_DIR / "SHOTS.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="regenerate in memory and fail if any committed file differs")
    ap.add_argument("--import-shots", metavar="DIR", help="import a capture_site_shots.mjs run into docs/assets/readme/app/")
    ap.add_argument("--write-readme", action="store_true",
                    help="rewrite README.md's generated blocks (badges, numbers) and every picture's alt text from its source")
    args = ap.parse_args()
    if args.import_shots:
        import_shots(Path(args.import_shots))
        return 0
    why = history_problem()
    if why:
        print(f"gen_readme_assets: {why}. Each figure names the commit of its source files, so it cannot be built "
              "or checked without the repository's git history. Clone https://github.com/ashfordeOU/SetuHQ with its "
              "full history (git clone, or fetch-depth: 0 in CI) and run this again.", file=sys.stderr)
        return 2
    assets = build()
    if args.write_readme:
        text = README.read_text(encoding="utf-8")
        new = render_readme(text, assets)
        README.write_text(new, encoding="utf-8")
        print("README.md " + ("rewritten" if new != text else "already current"))
        return 0
    if args.check:
        man_key = f"{REL_OUT}/MANIFEST.json"

        def same(n: str, b: bytes) -> bool:
            if not (ROOT / n).exists():
                return False
            if n != man_key:
                return (ROOT / n).read_bytes() == b
            a_, b_ = json.loads((ROOT / n).read_text(encoding="utf-8")), json.loads(b)
            a_.pop("made_with", None)
            b_.pop("made_with", None)
            return a_ == b_

        stale = [n for n, b in assets.items() if not same(n, b)]
        extra = sorted(p.relative_to(ROOT).as_posix() for d in (OUT, BRAND_DIR) for p in d.glob("*")
                       if p.is_file() and p.name != "README.md" and p.relative_to(ROOT).as_posix() not in assets
                       and p.relative_to(ROOT).as_posix() != SOCIAL_PNG)   # checked by check_social_card
        for n in stale:
            print(f"stale: {n} (regenerate with python3 tools/gen_readme_assets.py, then --write-readme)")
        if stale and (ROOT / man_key).exists():
            was = json.loads((ROOT / man_key).read_text(encoding="utf-8")).get("made_with", {})
            now = made_with()
            print("  the committed files were made with " + ", ".join(f"{k} {v}" for k, v in was.items())
                  + "; this environment has " + ", ".join(f"{k} {v}" for k, v in now.items())
                  + (" (different versions can change the outlines: pip install -r requirements-readme.txt)" if was != now else ""))
        for n in extra:
            print(f"not generated by this script: {n}")
        problems = check_readme(assets) + check_shots(assets)
        text = README.read_text(encoding="utf-8")
        if render_readme(text, assets) != text:
            problems.append("README: its badges, generated numbers or alt text differ from the data; "
                            "run python3 tools/gen_readme_assets.py --write-readme")
        for p in problems:
            print(p)
        if not (stale or extra or problems):
            print(f"gen_readme_assets --check: {len(assets)} files current; README and screenshots consistent "
                  f"({', '.join(f'{k} {v}' for k, v in made_with().items())})")
        return 1 if stale or extra or problems else 0
    total = 0
    for n, b in sorted(assets.items()):
        (ROOT / n).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / n).write_bytes(b)
        total += len(b)
        print(f"{len(b):>9,}  {n}")
    print(f"{total:>9,}  total")
    return 0


if __name__ == "__main__":
    sys.exit(main())

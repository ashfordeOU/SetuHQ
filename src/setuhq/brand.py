# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The SetuHQ brand on the built pages: the logo, the favicon, the social card and the page metadata.

The files themselves are made by ``tools/gen_readme_assets.py`` into ``docs/assets/brand/`` (the social
card's PNG is rasterised from its SVG by ``tools/capture_site_shots.mjs``). A page build copies the ones it
uses into its own ``assets/brand/`` folder, as it does with its fonts, so every page works from wherever it
is served, and refers to them with relative paths. Only the social card has an absolute address, because
link previews need one: :data:`SITE_URL` plus the app's copy.

"SetuHQ" and the Setu mark are trademarks of Ashforde OÜ (TRADEMARKS.md).
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

SITE_URL = "https://setuhq.com"
NAME = "SetuHQ"
TAGLINE = "The open exoplanet observatory: from public sky data to reviewed, explained candidates."
BRAND_SRC = Path(__file__).resolve().parents[2] / "docs" / "assets" / "brand"
ASSETS = "assets/brand/"
LOGO_DARK = "setuhq-logo-dark.svg"      # for dark grounds (the app's default theme)
LOGO_LIGHT = "setuhq-logo-light.svg"
FAVICON = "setuhq-favicon.svg"
SOCIAL_CARD = "setuhq-social-card.png"
# The lockup's own size (docs/assets/brand/setuhq-logo-*.svg), so the image reserves its box before it loads.
LOGO_W, LOGO_H = 579, 132
# Where the deployed site serves the social card: the app's copy (site/app/assets/brand/).
SOCIAL_CARD_URL = f"{SITE_URL}/app/{ASSETS}{SOCIAL_CARD}"
SOCIAL_CARD_ALT = ("The SetuHQ logo on navy, with the line The open exoplanet observatory: from public sky data to "
                   "reviewed, explained candidates, and setuhq.com.")

# The logo shows the variant for the page's theme: dark by default, light under data-theme="light", and the
# system's choice under data-theme="system". Pages without a theme control show the dark variant on their own
# dark ground unless they say otherwise.
LOGO_CSS = (".brandlogo{display:block;height:24px;width:auto}.brandlogo.lt{display:none}"
            ":root[data-theme=\"light\"] .brandlogo.dk{display:none}:root[data-theme=\"light\"] .brandlogo.lt{display:block}"
            "@media (prefers-color-scheme: light){:root[data-theme=\"system\"] .brandlogo.dk{display:none}"
            ":root[data-theme=\"system\"] .brandlogo.lt{display:block}}")


def available() -> bool:
    """True when the brand files are in this checkout (they are not in an installed wheel)."""
    return (BRAND_SRC / LOGO_DARK).exists() and (BRAND_SRC / FAVICON).exists()


def copy_assets(out_dir: str | Path, *, social_card: bool = False) -> list[Path]:
    """Copy the logo, the favicon (and, for the app, the social card's PNG) into ``out_dir/assets/brand/``."""
    if not available():
        return []
    dest = Path(out_dir) / ASSETS
    dest.mkdir(parents=True, exist_ok=True)
    names = [LOGO_DARK, LOGO_LIGHT, FAVICON] + ([SOCIAL_CARD] if social_card else [])
    out = []
    for n in names:
        if (BRAND_SRC / n).exists():
            out.append(Path(shutil.copyfile(BRAND_SRC / n, dest / n)))
    return out


def logo(prefix: str = "", *, themed: bool = True) -> str:
    """The lockup as images (dark and light variants, one shown by :data:`LOGO_CSS`); text when the files are absent."""
    if not available():
        return f'<span class="brandname">{NAME}</span>'
    dk = f'<img class="brandlogo dk" src="{html.escape(prefix + ASSETS + LOGO_DARK)}" alt="{NAME}" width="{LOGO_W}" height="{LOGO_H}">'
    if not themed:
        return dk
    lt = f'<img class="brandlogo lt" src="{html.escape(prefix + ASSETS + LOGO_LIGHT)}" alt="{NAME}" width="{LOGO_W}" height="{LOGO_H}">'
    return dk + lt


def head(title: str, description: str, path: str, *, prefix: str = "") -> str:
    """Favicon, description, canonical address, Open Graph and Twitter card tags for a page served at ``path``
    (for example ``"/"`` or ``"/app/"``), with its brand files under ``prefix + "assets/brand/"``."""
    e = html.escape
    url = SITE_URL + path
    icon = (f'<link rel="icon" type="image/svg+xml" href="{e(prefix + ASSETS + FAVICON)}">' if available()
            else '<link rel="icon" href="data:,">')
    return (f'{icon}\n<meta name="description" content="{e(description)}">\n'
            f'<link rel="canonical" href="{e(url)}">\n'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="{NAME}">'
            f'<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(description)}">'
            f'<meta property="og:url" content="{e(url)}"><meta property="og:image" content="{SOCIAL_CARD_URL}">'
            f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta property="og:image:alt" content="{e(SOCIAL_CARD_ALT)}">\n'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}">'
            f'<meta name="twitter:description" content="{e(description)}"><meta name="twitter:image" content="{SOCIAL_CARD_URL}">')


def page_path(out_dir: str | Path) -> str:
    """The address a page built into ``out_dir`` has on the site, by the layout scripts/ci_local.sh builds:
    site/<name>/index.html is served at /<name>/."""
    return f"/{Path(out_dir).resolve().name}/"

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The SetuHQ brand on the pages: the logo, favicon and social card are copied beside each page, and every page
names its canonical address at https://setuhq.com with Open Graph and Twitter card tags."""

import re
from pathlib import Path

from setuhq import brand

ROOT = Path(__file__).resolve().parents[1]


def test_head_names_the_canonical_address_and_an_absolute_social_card():
    head = brand.head("SetuHQ: the sky, reviewed", "A <test> page", "/", prefix="app/")
    assert '<link rel="canonical" href="https://setuhq.com/">' in head
    assert '<meta property="og:image" content="https://setuhq.com/app/assets/brand/setuhq-social-card.png">' in head
    assert '<meta name="twitter:card" content="summary_large_image">' in head
    assert 'href="app/assets/brand/setuhq-favicon.svg"' in head and "A &lt;test&gt; page" in head
    assert brand.page_path("/x/site/docket") == "/docket/"


def test_copied_assets_are_the_brand_kit(tmp_path):
    out = brand.copy_assets(tmp_path, social_card=True)
    names = {p.name for p in out}
    assert {"setuhq-logo-dark.svg", "setuhq-logo-light.svg", "setuhq-favicon.svg"} <= names
    for p in out:
        assert p.read_bytes() == (ROOT / "docs/assets/brand" / p.name).read_bytes()
    logo = brand.logo("../")
    assert 'src="../assets/brand/setuhq-logo-dark.svg"' in logo and 'alt="SetuHQ"' in logo


def test_the_committed_site_serves_from_the_domain_root():
    site = ROOT / "site"
    assert (site / "CNAME").read_text().strip() == "setuhq.com"
    for page, path in (("index.html", "/"), ("app/index.html", "/app/"), ("docket/index.html", "/docket/"),
                       ("plate/index.html", "/plate/"), ("report/index.html", "/report/")):
        text = (site / page).read_text(encoding="utf-8")
        assert f'<link rel="canonical" href="https://setuhq.com{path}">' in text, page
        assert "og:image" in text and "twitter:card" in text, page
        assert "/EXOPLAN/" not in text and "exoplan-theme" not in text, page
        # every brand file a page names is beside it
        for ref in set(re.findall(r'(?:src|href)="([^"]*assets/brand/[^"]+)"', text)):
            assert (site / page).parent.joinpath(ref).resolve().exists(), (page, ref)
    assert (site / "app/assets/brand/setuhq-social-card.png").exists()


def test_no_page_or_template_carries_an_assistant_meta_tag_or_a_session_url():
    """The built site and the page generators name no AI tool in their markup: no claude:* meta tag, no claude.ai URL."""
    pat = re.compile(r'<meta[^>]+name=["\']claude:|claude\.ai', re.I)
    files = [p for p in (ROOT / "site").rglob("*") if p.suffix in (".html", ".js", ".css", ".json")]
    files += sorted((ROOT / "src" / "setuhq").rglob("*.py"))
    bad = [str(p.relative_to(ROOT)) for p in files if pat.search(p.read_text(encoding="utf-8", errors="replace"))]
    assert not bad, bad

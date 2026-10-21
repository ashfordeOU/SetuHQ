# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The website: one clean address per page, every old address forwarded, each page's own metadata, the shared
files and the page budget, the header, the home page, and no site-wide banner."""

import html as html_mod
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import brand
from setuhq.codenote import PRE_FIX_NOTE, VISITOR_TEXT, visitor_note, with_code_note
from setuhq.methods import CHAPTERS
from setuhq.names import ATTRIBUTION
from setuhq.routes import (ALIASES, CHAPTER_SLUGS, LEGACY_PAGES, ROUTE_PATHS, ROUTES_CORE_JS, from_hash, legacy_target,
                           parse_path, route_table, url_for)
from setuhq.site import PAGE_BUDGET, check_budget

LEAD = "tess-x-001"


def test_every_view_has_one_clean_address_and_back():
    for route, path in ROUTE_PATHS.items():
        assert path.startswith("/") and path.endswith("/") and "#" not in path
        assert url_for(route) == path
        if route != "methods":
            assert parse_path(path) == {"route": route, "params": {}}
    for cid, _ in CHAPTERS:
        path = url_for("methods", {"ch": cid})
        assert parse_path(path) == {"route": "methods", "params": {"ch": cid}}
    assert url_for("methods", {"ch": "survey"}) == "/how-it-works/" and url_for("methods", {"ch": "rv"}) == "/how-it-works/radial-velocity/"
    assert len(set(CHAPTER_SLUGS.values())) == len(CHAPTERS)
    assert url_for("transit", {"dip": "tess-a-001"}) == "/candidates/tess-a-001/"
    assert url_for("candidates", {"dip": "tess-a-001", "section": "ledger"}) == "/candidates/tess-a-001/case-file/#ledger"
    assert parse_path("/candidates/tess-a-001/case-file/") == {"route": "candidates", "params": {"dip": "tess-a-001"}}
    assert parse_path("/planets/pi-men-c/") == {"route": "planet", "params": {"id": "pi-men-c"}}
    assert parse_path("/stars/pi-men/") == {"route": "star", "params": {"id": "pi-men"}}
    # A deep link keeps its view query; the address bar's copy (keep_query=False) drops it.
    assert url_for("galaxy", {"focus": "pi Men"}) == "/explore/galaxy/?focus=pi+Men"
    assert url_for("galaxy", {"focus": "pi Men"}, keep_query=False) == "/explore/galaxy/"
    # Not a page: the stand-alone case file is its own page, outside the app; nonsense is nothing.
    for path in ("/candidates/case-file/", "/nope/", "/planets/", "/how-it-works/nope/", "/planets/Pi Men/"):
        assert parse_path(path) is None, path


OLD = [("#/", "/"), ("#/overview?layout=kpis.L,discoveries.M,runs.M,top.L", "/"), ("#/sky", "/explore/"),
       ("#/galaxy?focus=pi%20Men", "/explore/galaxy/?focus=pi+Men"), ("#/catalogue", "/catalogue/"),
       ("#/variables?class=eclipse", "/catalogue/everything-that-dims/?class=eclipse"), ("#/mission", "/explore/mission-control/"),
       ("#/transit", f"/candidates/{LEAD}/"), ("#/transit?dip=tess-y-002", "/candidates/tess-y-002/"),
       ("#/explorer?sort=depth&filter=new", "/candidates/?sort=depth&filter=new"), ("#/candidates", f"/candidates/{LEAD}/case-file/"),
       ("#/candidates?dip=tess-y-002&section=ledger", "/candidates/tess-y-002/case-file/#ledger"),
       ("#/planets", "/candidates/radius-ratios/"), ("#/sentinels", "/evidence/"), ("#/leaderboard", "/evidence/leaderboard/"),
       ("#/runs", "/evidence/runs/"), ("#/methods", "/how-it-works/"), ("#/methods?ch=spectroscopy", "/how-it-works/atmospheres/"),
       ("#/planet/pi-men-c", "/planets/pi-men-c/"), ("#/star/pi-men", "/stars/pi-men/"), ("#/discoveries", "/candidates/"),
       ("#/feed", "/candidates/"), ("#/panel", "/evidence/"), ("#/home", "/explore/"), ("#/cockpit", f"/candidates/{LEAD}/"),
       ("#/about", "/"), ("#/no-such-thing", "/")]


def test_every_old_address_forwards():
    for h, new in OLD:
        assert legacy_target("/app/", h, lead=LEAD) == new, h
    assert set(ALIASES) == {"discoveries", "feed", "panel", "home", "cockpit", "about"}
    assert legacy_target("/app/", "", lead=LEAD) == "/"
    assert legacy_target("/docket/", "#tess-y-002") == "/candidates/tess-y-002/case-file/"
    assert legacy_target("/docket/", "") == "/candidates/case-file/"
    assert legacy_target("/plate/", "#tic-1") == "/evidence/plates/#tic-1"
    assert legacy_target("/report", "") == "/evidence/report/"
    assert legacy_target("/dashboard/") == legacy_target("/discoveries/") == "/candidates/"
    assert legacy_target("/no-such-page/", "#/galaxy") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_pages_copy_of_the_address_rules_agrees():
    paths = sorted(set(ROUTE_PATHS.values()) | {url_for("methods", {"ch": c}) for c, _ in CHAPTERS}
                   | {"/candidates/tess-a-001/", "/candidates/tess-a-001/case-file/", "/planets/pi-men-c/", "/nope/", "/candidates/case-file/"})
    hashes = [h for h, _ in OLD]
    legacy = [("/docket/", "#tess-y-002"), ("/docket/", ""), ("/plate/", "#t"), ("/report", ""), ("/dashboard/", ""), ("/x/", "#/sky")]
    script = (f"const RT = {json.dumps(route_table(LEAD))};\n{ROUTES_CORE_JS}\n"
              f"console.log(JSON.stringify({{parse: {json.dumps(paths)}.map(p => rtParse(p, '')), "
              f"hash: {json.dumps(hashes)}.map(h => rtFromHash(h, true)), legacy: {json.dumps(legacy)}.map(([p, h]) => rtLegacy(p, h))}}));")
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out["parse"] == [parse_path(p) for p in paths]
    assert out["hash"] == [legacy_target("/app/", h, lead=LEAD) for h in hashes]
    assert out["legacy"] == [legacy_target(p, h, lead=LEAD) for p, h in legacy]


@pytest.fixture(scope="module")
def site(pi_men_app):
    return Path(pi_men_app).parent


def _pages(site: Path) -> list[str]:
    return json.loads((site / "assets" / "pages.json").read_text())


def test_each_page_has_its_own_address_title_and_preview(site):
    pages = _pages(site)
    for p in ("/", "/explore/", "/explore/galaxy/", "/explore/mission-control/", "/catalogue/", "/catalogue/everything-that-dims/",
              "/candidates/", "/candidates/radius-ratios/", "/how-it-works/", "/how-it-works/radial-velocity/", "/evidence/",
              "/evidence/leaderboard/", "/evidence/runs/", "/docs/", "/planets/pi-men-c/", "/stars/pi-men/"):
        assert p in pages, p
    dips = json.loads(next(site.glob("assets/data/app-*.json")).read_text())["dossier_ids"]
    for d in dips:
        assert f"/candidates/{d}/" in pages and f"/candidates/{d}/case-file/" in pages
    assert sum(p.startswith("/how-it-works/") for p in pages) == len(CHAPTERS)
    titles = set()
    for p in pages:
        html = (site / p.strip("/") / "index.html").read_text()
        title = re.search(r"<title>([^<]+)</title>", html).group(1)
        titles.add(title)
        assert f'<link rel="canonical" href="{brand.SITE_URL}{p}">' in html, p
        assert f'<meta property="og:url" content="{brand.SITE_URL}{p}">' in html, p
        assert f'<meta property="og:image" content="{brand.SITE_URL}/assets/brand/setuhq-social-card.png">' in html
        assert re.search(r'<meta name="description" content="[^"]{30,}">', html), p
        # Its own view is in the HTML (readable without JavaScript), and nothing links to an old #/ address.
        assert re.search(r'<section class="route" id="route-\w+"[^>]*>\s*<header[^>]*>.*?<h1', html, re.S), p
        assert 'href="#/' not in html, p
    assert len(titles) == len(pages)  # no two pages share a title
    assert (site / "assets" / "brand" / "setuhq-social-card.png").exists()
    assert 'href="#/' not in next(site.glob("assets/views-*.html")).read_text()


def test_pages_stay_within_the_budget_and_share_cached_files(site):
    assert check_budget(site) == []
    home = (site / "index.html").read_text()
    assert len(home) < PAGE_BUDGET < 1_400_000 // 5
    for pattern in ("assets/site-*.css", "assets/site-*.js", "assets/data/app-*.json", "assets/views-*.html"):
        files = list(site.glob(pattern))
        assert len(files) == 1 and re.search(r"-[0-9a-f]{10}\.", files[0].name), pattern  # named by content: cached for good
        assert f'/{files[0].relative_to(site).as_posix()}"' in home or pattern.endswith((".json", ".html")), pattern
    # The pages differ only in their own view: the shell, the script and the data are shared.
    assert "<script>" not in home.split('<script src="')[0].split("</title>")[1].replace("<script>(function(){var t='dark'", "")


def test_sitemap_robots_404_and_forwarding_pages(site):
    pages = _pages(site)
    sitemap = (site / "sitemap.xml").read_text()
    assert all(f"<loc>{brand.SITE_URL}{p}</loc>" in sitemap for p in pages)
    assert "Sitemap: https://setuhq.com/sitemap.xml" in (site / "robots.txt").read_text()
    nf = (site / "404.html").read_text()
    assert '<meta name="robots" content="noindex">' in nf and 'rel="canonical"' not in nf
    assert "rtLegacy(location.pathname,location.hash)" in nf and "This page is not here." in nf
    for p in ("/", "/explore/", "/candidates/", "/how-it-works/", "/evidence/", "/docs/"):
        assert f'href="{p}"' in nf, p
    for old, new in LEGACY_PAGES.items():
        fwd = (site / old.strip("/") / "index.html").read_text()
        assert f'url={new}"' in fwd and "rtLegacy(" in fwd and "noindex" in fwd, old


def test_the_header_is_five_plain_sections_search_theme_and_a_menu(site):
    home = (site / "index.html").read_text()
    top = re.search(r'<header class="topbar">.*?</header>', home, re.S).group(0)
    labels = re.findall(r'<a href="[^"]+" data-nav="\w+">([^<]+)</a>', re.search(r'<nav class="nav".*?</nav>', top, re.S).group(0))
    assert labels == ["Explore", "Candidates", "How it works", "Evidence", "Docs"]
    assert 'aria-label="SetuHQ, home"' in top and 'href="/"' in top
    assert 'id="gsearchbtn"' in top and 'aria-haspopup="dialog"' in top
    assert "data-theme-toggle" in top and "Dark (default)" not in home and "themelbl" not in home
    assert 'id="menubtn" aria-expanded="false" aria-controls="menu"' in top
    # No run chip, no duplicate page label; breadcrumbs only on deep pages.
    assert "Sector 1" not in top and "curlabel" not in home and 'class="eyebrow"' not in re.search(r'id="route-overview".*?</header>', home, re.S).group(0)
    assert '<nav class="crumbs" id="crumbs" aria-label="Breadcrumb" hidden>' in home
    assert '<nav class="crumbs" id="crumbs" aria-label="Breadcrumb"><ol>' in (site / "explore" / "galaxy" / "index.html").read_text()
    assert '<nav class="crumbs" id="crumbs" aria-label="Breadcrumb" hidden>' in (site / "explore" / "index.html").read_text()
    css = next(site.glob("assets/site-*.css")).read_text()
    assert "env(safe-area-inset-top" in css and ".topbar{display:block;position:sticky;top:0" in css
    assert "@media (max-width:899.98px){\n  .nav{display:none}\n  .menubtn{display:inline-grid}" in css


def test_the_home_page(site):
    home = (site / "index.html").read_text()
    hero = re.search(r'<header class="launch">.*?</header>', home, re.S).group(0)
    assert '<p class="kick">' not in hero and "<h1" in hero
    fig = re.search(r'<figure class="planetfig">.*?</figure>', home, re.S).group(0)
    assert re.search(r"</svg>\s*<figcaption>Artist's impression", fig)  # the caption right under its image
    row = re.search(r'<section class="dohere".*?</section>', home, re.S).group(0)
    for href in ("/explore/", "/candidates/", "/how-it-works/", "/evidence/", "/docs/"):
        assert f'href="{href}"' in row, href
    assert home.index('class="dohere"') < home.index('class="proof"')
    assert ATTRIBUTION in home  # in the footer of every page
    assert ATTRIBUTION in (site / "evidence" / "index.html").read_text()


def test_no_site_wide_banner_and_one_quiet_sentence_where_it_applies(site):
    pages = _pages(site)
    note = json.loads(Path("runs/tess-pi-men-s1/manifest.json").read_text()).get("code_note")
    with_note = {"/candidates/", "/candidates/radius-ratios/", "/evidence/", "/evidence/runs/"}
    for p in pages:
        html = (site / p.strip("/") / "index.html").read_text()
        plain = html_mod.unescape(html).replace(PRE_FIX_NOTE, "")  # the Docs page quotes the technical note, once
        assert 'id="codenote"' not in html and "5a03087" not in plain and "preprocess.clean" not in plain, p
        if note and (p in with_note or p.endswith("/case-file/") and p != "/candidates/case-file/"):
            assert html.count(VISITOR_TEXT) == 1 and 'href="/docs/#provenance">Details</a>' in html, p
        if p in ("/", "/explore/galaxy/", "/catalogue/", "/how-it-works/", "/planets/pi-men-c/"):
            assert VISITOR_TEXT not in html, p
    docs = (site / "docs" / "index.html").read_text()
    assert 'id="provenance"' in docs and (not note or note in html_mod.unescape(docs))


def test_quiet_note_helpers():
    assert visitor_note(None) == "" and with_code_note("<body><h1>x</h1></body>", None) == "<body><h1>x</h1></body>"
    out = with_code_note("<body><main><h1>Title</h1><p>x</p></main></body>", PRE_FIX_NOTE)
    assert out.index("</h1>") < out.index(VISITOR_TEXT) < out.index("<p>x")
    assert "5a03087" not in out and "preprocess" not in out and "background" not in out
    assert "confirmed" not in VISITOR_TEXT.lower()

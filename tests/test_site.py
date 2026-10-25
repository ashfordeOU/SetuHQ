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
from setuhq.routes import (ALIASES, CHAPTER_SLUGS, DIP_SLUGS, LEGACY_PAGES, ROUTE_PATHS, ROUTES_CORE_JS, from_hash,
                           legacy_target, parse_path, route_table, set_dip_slugs, url_for)
from setuhq.stubs import write_stubs
from setuhq.site import PAGE_BUDGET, SHELL_BUDGET, STUB_BUDGET, check_asset_budget, check_budget

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
    # A dip's address is readable: its star and its number, never the stored id.
    keep = dict(DIP_SLUGS)
    set_dip_slugs({"tess-a-001": "pi-men/dip-1"})
    try:
        assert url_for("transit", {"dip": "tess-a-001"}) == "/candidates/pi-men/dip-1/"
        assert url_for("candidates", {"dip": "tess-a-001", "section": "ledger"}) == "/candidates/pi-men/dip-1/case-file/#ledger"
        assert parse_path("/candidates/pi-men/dip-1/") == {"route": "transit", "params": {"dip": "tess-a-001"}}
        assert parse_path("/candidates/pi-men/dip-1/case-file/") == {"route": "candidates", "params": {"dip": "tess-a-001"}}
        assert parse_path("/candidates/tess-a-001/") is None
        assert route_table(None)["dips"] == {"tess-a-001": "pi-men/dip-1"}
    finally:
        set_dip_slugs(keep)
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
    data = json.loads(next(site.glob("assets/data/app-*.json")).read_text())
    for d in data["dossier_ids"]:
        slug = data["routes"]["dips"][d]
        assert re.fullmatch(r"[a-z0-9-]+/dip-\d+", slug), slug
        assert f"/candidates/{slug}/" in pages and f"/candidates/{slug}/case-file/" in pages
        assert f"/candidates/{d}/" not in pages
        label = data["dips"][d]["label"]  # e.g. "pi Men, dip 2 (6.27 d)"
        assert re.fullmatch(r".+, dip \d+( \([\d.]+ d\))?", label), label
        assert html_mod.escape(label, quote=False) in (site / "candidates" / slug / "index.html").read_text()
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
    sitemap = (site / "sitemap-pages.xml").read_text()
    assert all(f"<loc>{brand.SITE_URL}{p}</loc>" in sitemap for p in pages)
    assert f"<sitemapindex" in (index := (site / "sitemap.xml").read_text()) and f"{brand.SITE_URL}/sitemap-pages.xml" in index
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
    # The hero is the featured run's transit (setuhq.viz.hero): a still with alt text, its tag and its caption.
    fig = re.search(r'<figure class="stage rfig herofig".*?</figure>', hero, re.S).group(0)
    assert 'data-render="transit"' in fig and "Artist&#x27;s impression</a>" in fig and "Model from stored values." in fig
    assert 'class="planetfig"' not in home and 'class="gxteaser' not in home
    row = re.search(r'<section class="dohere".*?</section>', home, re.S).group(0)
    for href in ("/explore/", "/candidates/", "/how-it-works/", "/evidence/", "/docs/"):
        assert f'href="{href}"' in row, href
    assert home.index('class="proof"') < home.index('class="dohere"')
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


def _visible_text(html: str) -> str:
    html = re.sub(r"<(script|style|template)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->|<[^>]+>", " ", html, flags=re.S)
    return html_mod.unescape(html)


def test_no_old_project_name_in_what_a_visitor_reads(site):
    """The project was once called exoplan. Stored records keep that name (they are hashed and are not edited), but the
    pages map it to SetuHQ when they draw them. Only the history note ("then called exoplan") and the technical pages,
    which quote a stored record verbatim, may show it."""
    technical = {"/docs/", "/evidence/runs/", "/evidence/report/"}
    pages = _pages(site) + ["/evidence/plates/", "/evidence/report/", "/candidates/case-file/"]
    for p in pages:
        if p in technical or not (site / p.strip("/") / "index.html").exists():  # the stand-alone pages: built by setuhq site
            continue
        text = _visible_text((site / p.strip("/") / "index.html").read_text()).replace(PRE_FIX_NOTE, "")
        old = [m for m in re.findall(r".{0,40}\bexoplan\b.{0,20}", text, re.I) if "then called exoplan" not in m.lower()]
        assert not old, (p, old[:3])
    # The app's views, drawn into every page by the script, are held to the same rule outside the Docs section.
    views = next(site.glob("assets/views-*.html")).read_text()
    views = re.sub(r'<section class="route" id="route-(docs|runs)".*?</section>\s*(?=<section class="route"|$)', "", views, flags=re.S)
    old = [m for m in re.findall(r".{0,40}\bexoplan\b.{0,20}", _visible_text(views).replace(PRE_FIX_NOTE, ""), re.I)
           if "then called exoplan" not in m.lower()]
    assert not old, old[:3]


def test_public_name_maps_the_old_name():
    from setuhq.names import public_name, public_text
    assert public_name("exoplan") == public_name(" Exoplan ") == "SetuHQ" and public_name("ada") == "ada"
    assert "exoplan" not in public_text("exoplan 0.4 (src/exoplan/search.py)").lower()
    assert public_text("printed by 'exoplan calibrate'") == "printed by 'setuhq calibrate'"


def test_every_catalogue_planet_and_star_gets_a_small_page(site, tmp_path):
    """setuhq.stubs, run at deploy time on a copy of the site: a page for every planet and star without one."""
    for rel in ("assets/stub-template.html", "assets/data/catalogue.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(site / rel, tmp_path / rel)
    (tmp_path / "planets" / "pi-men-c").mkdir(parents=True)
    (tmp_path / "planets" / "pi-men-c" / "index.html").write_text("pre-rendered")
    r = write_stubs(tmp_path)
    cat = json.loads((tmp_path / "assets/data/catalogue.json").read_text())
    assert r["planets"] == len(cat["planets"]["name"]) - 1 and r["stars"] > 1000
    assert (tmp_path / "planets" / "pi-men-c" / "index.html").read_text() == "pre-rendered"  # a real page wins
    assert r["bytes_max"] <= 4_096  # each stub stays small (site.STUB_BUDGET), its portrait slot included
    i = cat["planets"]["slug"].index("kepler-22-b")
    page = (tmp_path / "planets" / "kepler-22-b" / "index.html").read_text()
    name = cat["planets"]["name"][i]
    assert f"<title>{name} · Planets · SetuHQ</title>" in page and f'<link rel="canonical" href="{brand.SITE_URL}/planets/kepler-22-b/">' in page
    assert re.search(rf"<h1[^>]*>{re.escape(name)}</h1>", page) and "{{" not in page
    assert 'data-route="planet"' in page or "data-chrome" in page
    star = (tmp_path / "stars" / "kepler-22" / "index.html").read_text()
    assert "<title>Kepler-22 · Stars · SetuHQ</title>" in star and "known planet" in star
    index = (tmp_path / "sitemap.xml").read_text()
    for f in ("sitemap-pages.xml", "sitemap-planets-1.xml", "sitemap-stars-1.xml"):
        assert f"{brand.SITE_URL}/{f}" in index
    assert f"<loc>{brand.SITE_URL}/planets/kepler-22-b/</loc>" in (tmp_path / "sitemap-planets-1.xml").read_text()
    assert "/planets/pi-men-c/" not in (tmp_path / "sitemap-planets-1.xml").read_text()


def _dip(i, t, subject="s1", target="TIC 1", dur=2.0):
    return {"candidate_id": i, "t_start": t - 0.05, "t_center": t, "subject_id": subject, "target": target,
            "duration_hours": dur, "period_days": None}


def test_dip_addresses_are_pinned_per_star_and_never_renumbered(tmp_path):
    from setuhq import dipslugs
    from setuhq.app import dip_names, pin_run_dips

    names = {"TIC 1": "pi Men", "TIC 2": "HD 1"}
    first, gone = pin_run_dips(tmp_path, [_dip("s1-000", 3), _dip("s1-001", 1), _dip("s2-000", 2, "s2", "TIC 2")], names)
    assert {i: d["slug"] for i, d in first.items()} == {"s1-001": "pi-men/dip-1", "s1-000": "pi-men/dip-2", "s2-000": "hd-1/dip-1"}
    assert gone == [] and first["s1-000"]["label"] == "pi Men, dip 2"
    saved = dipslugs.load(tmp_path)
    assert {e["slug"]: (e["subject"], e["t_center"], e["star"]) for e in saved}["pi-men/dip-2"] == ("s1", 3, "pi Men")
    # A rebuilt run: the dip at t=1 is gone and a new one at t=0.5 appears, earlier than the rest. Nobody is
    # renumbered; the new dip gets the next number of its star, and the gone address is not given to anyone.
    again, gone = pin_run_dips(tmp_path, [_dip("s1-000", 3), _dip("s1-001", 0.5), _dip("s2-000", 2, "s2", "TIC 2")], names)
    assert again["s1-000"]["slug"] == "pi-men/dip-2" and again["s1-001"]["slug"] == "pi-men/dip-3" and gone == ["pi-men/dip-1"]
    assert [e["slug"] for e in dipslugs.load(tmp_path)] == ["hd-1/dip-1", "pi-men/dip-1", "pi-men/dip-2", "pi-men/dip-3"]
    # Same input again: nothing changes, nothing is written.
    assert pin_run_dips(tmp_path, [_dip("s1-000", 3), _dip("s1-001", 0.5), _dip("s2-000", 2, "s2", "TIC 2")], names)[1] == ["pi-men/dip-1"]
    assert dip_names([], names)[0] == {}


def test_an_older_slugs_file_is_read_by_id_once_then_pinned_by_time(tmp_path):
    from setuhq import dipslugs
    from setuhq.app import pin_run_dips

    (tmp_path / "slugs.json").write_text(json.dumps({"slugs": {"s1-000": "pi-men/dip-4"}}))
    names, gone = pin_run_dips(tmp_path, [_dip("s1-000", 10.0), _dip("s1-001", 20.0)], {"TIC 1": "pi Men"})
    assert names["s1-000"]["slug"] == "pi-men/dip-4" and names["s1-001"]["slug"] == "pi-men/dip-5" and gone == []
    assert {e["slug"]: e["t_center"] for e in dipslugs.load(tmp_path)} == {"pi-men/dip-4": 10.0, "pi-men/dip-5": 20.0}


def test_an_address_follows_its_dip_not_its_rank(tmp_path):
    """A candidate id is {subject}-{rank}: a re-run that ranks two dips the other way swaps their ids. Each address
    stays with its dip (same subject, same mid-time within its duration)."""
    from setuhq.app import pin_run_dips

    names = {"TIC 1": "pi Men"}
    before, _ = pin_run_dips(tmp_path, [_dip("s1-000", 10.0), _dip("s1-001", 20.0)], names)
    assert before["s1-000"]["slug"] == "pi-men/dip-1" and before["s1-001"]["slug"] == "pi-men/dip-2"
    swapped, gone = pin_run_dips(tmp_path, [_dip("s1-001", 10.001), _dip("s1-000", 20.0)], names)
    assert swapped["s1-001"]["slug"] == "pi-men/dip-1" and swapped["s1-000"]["slug"] == "pi-men/dip-2" and gone == []
    # A dip that moved by more than its duration is not the same dip: its address is gone and it gets a new number.
    moved, gone = pin_run_dips(tmp_path, [_dip("s1-001", 10.001), _dip("s1-000", 20.3)], names)
    assert moved["s1-001"]["slug"] == "pi-men/dip-1" and moved["s1-000"]["slug"] == "pi-men/dip-3" and gone == ["pi-men/dip-2"]
    # Two dips half a day apart in one subject (as pi Men's dip 5 and dip 6): each keeps its own address.
    tmp2 = tmp_path / "close"
    tmp2.mkdir()
    a, _ = pin_run_dips(tmp2, [_dip("s1-000", 48.38, dur=9.9), _dip("s1-001", 48.94, dur=0.9)], names)
    b, _ = pin_run_dips(tmp2, [_dip("s1-001", 48.38, dur=9.9), _dip("s1-000", 48.94, dur=0.9)], names)
    assert a["s1-000"]["slug"] == b["s1-001"]["slug"] and a["s1-001"]["slug"] == b["s1-000"]["slug"]


def test_the_pi_men_run_keeps_its_seven_addresses(site):
    """runs/tess-pi-men-s1/slugs.json pins dip-1 to dip-7 to the dips by subject and mid-time; the run as stored maps
    to them exactly (and so does the re-run on the fixed code, which has the same seven dips at the same times)."""
    from setuhq import dipslugs

    pinned = dipslugs.load("runs/tess-pi-men-s1")
    assert [e["slug"] for e in pinned] == [f"pi-men/dip-{n}" for n in range(1, 8)]
    assert all(e["subject"] and e["t_center"] and e["duration_hours"] for e in pinned)
    cands = json.loads(Path("runs/tess-pi-men-s1/candidates.json").read_text())
    slugs, gone, entries = dipslugs.pin(cands, pinned, lambda c: "pi-men")
    assert gone == [] and entries == pinned and sorted(slugs.values()) == [e["slug"] for e in pinned]
    data = json.loads(next(site.glob("assets/data/app-*.json")).read_text())
    assert data["routes"]["dips"] == slugs and data["routes"]["gone"] == []


def test_a_rejected_dip_is_never_called_a_candidate(site):
    data = json.loads(next(site.glob("assets/data/app-*.json")).read_text())
    outcome = {d["id"]: d["outcome"] for d in data["story"]["dips"]}
    assert "rejected" in outcome.values()
    for i, o in outcome.items():
        page = (site / "candidates" / data["routes"]["dips"][i] / "index.html").read_text()
        sub = re.search(r'<p id="txsub">(.*?)</p>', page).group(1)
        cap = re.search(r'<span id="txcapword">(.*?)</span>', page).group(1)
        if o == "rejected":
            assert "candidate, unconfirmed" not in sub and "not a candidate" in sub and cap == "The dip, played back", i
            assert "Candidate, unconfirmed" not in re.search(r'id="txscore".*?</section>', page, re.S).group(0)
        elif o == "passed":
            assert sub.endswith("candidate, unconfirmed") and cap == "The transit, played back", i
    cands = (site / "candidates" / "index.html").read_text()
    for i, o in outcome.items():
        row = re.search(rf'<a class="rundip" href="/candidates/{re.escape(data["routes"]["dips"][i])}/">.*?</a>', cands, re.S).group(0)
        assert {"passed": 'class="tag cand"', "flagged": 'class="tag open"', "rejected": 'class="tag rej"'}[o] in row, (i, row)


def test_shared_assets_stay_within_their_budgets(site):
    assert check_asset_budget(site) == []
    assert STUB_BUDGET == 4_096
    assert next((site / "assets").glob("render-*.js")).stat().st_size <= 64_000
    assert SHELL_BUDGET == 16_000 and next((site / "assets").glob("site-*.js")).stat().st_size <= SHELL_BUDGET
    assert len(list((site / "assets" / "render").glob("*/*.webp"))) == 36


def test_the_pictures_page_exists_with_one_heading_and_is_in_the_sitemap(site):
    page = (site / "docs" / "pictures" / "index.html").read_text()
    assert len(re.findall(r"<h1\b", page)) == 1 and "How the pictures are drawn." in page
    assert "/docs/pictures/" in json.loads((site / "assets" / "pages.json").read_text())
    assert f"<loc>{brand.SITE_URL}/docs/pictures/</loc>" in (site / "sitemap-pages.xml").read_text()
    assert page.count('data-render="planet"') == 18 and page.count('href="/docs/pictures/">Artist&#x27;s impression</a>') == 15
    assert page.count('href="/docs/pictures/">Illustration</a>') == 3  # the Solar System references
    assert "How the pictures are drawn ›" in (site / "index.html").read_text()  # the footer links it on every page
    assert url_for("pictures") == "/docs/pictures/" and parse_path("/docs/pictures/")["route"] == "pictures"


def test_no_page_loads_fonts_or_scripts_from_another_site(site):
    for f in site.rglob("*.html"):
        t = f.read_text()
        assert "fonts.googleapis" not in t and "fonts.gstatic" not in t, f
        assert not re.search(r'<script[^>]+src="(https?:)?//', t), f


def test_every_page_has_the_starfield_the_renderer_and_the_font_preload(site):
    page = (site / "index.html").read_text()
    assert re.search(r'<script src="/assets/render-[0-9a-f]+\.js" defer></script>', page)
    assert '<link rel="preload" href="/assets/fonts/files/geist-gyByhwUxId8gMEwcGFWNOITd.woff2" as="font" type="font/woff2" crossorigin>' in page
    assert '<div class="starfield" data-render="starfield"' in page and '<script type="speculationrules">' in page
    assert '<meta name="view-transition" content="same-origin">' in page
    assert "{{PORTRAIT}}" in (site / "assets" / "stub-template.html").read_text()


def test_the_shell_script_has_a_budget_of_its_own(tmp_path):
    """site-*.js (the shell, and SetuUI's figure utilities) is checked like the app's script and the stylesheet."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "site-0000000000.js").write_bytes(b"x" * SHELL_BUDGET)
    assert check_asset_budget(tmp_path) == []
    (tmp_path / "assets" / "site-0000000000.js").write_bytes(b"x" * (SHELL_BUDGET + 1))
    assert check_asset_budget(tmp_path) == [f"assets/site-0000000000.js: {SHELL_BUDGET + 1:,} bytes (budget {SHELL_BUDGET:,})"]

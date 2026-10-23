# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Honesty rule 3 (docs/SITE.md, "The visual system"): on the built site, SetuHQ's own output is never called
confirmed, discovered, a discovery or a new planet. Negations ("not a discovery", "never a confirmed planet") and
literature facts about catalogue planets are allowed. Runs over every page in pages.json and 200 deploy-time stubs."""

import html
import json
import random
import re
from pathlib import Path

import pytest

from setuhq.codenote import VISITOR_TEXT
from setuhq.names import ATTRIBUTION
from setuhq.stubs import planet_page, star_page

CLAIM = re.compile(r"\b(SetuHQ|this run|the panel|the pipeline|our|we)\b[^.]{0,60}?\b(confirm(?:ed|s)?|discover(?:ed|y|s)?|new planet)\b", re.I)
NEGATION = re.compile(r"\b(not|never|no|nothing)\b", re.I)
CLAUSE = ".;:!?"


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|template|noscript)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


def claims(text: str) -> list[str]:
    """Each claim the rule forbids, unless a negation sits in the same clause."""
    out = []
    for m in CLAIM.finditer(text):
        a = max(text.rfind(c, 0, m.start()) for c in CLAUSE)
        ends = [i for i in (text.find(c, m.end()) for c in CLAUSE) if i >= 0]
        clause = text[a + 1:min(ends) if ends else len(text)]
        if not NEGATION.search(clause):
            out.append(clause.strip()[:160])
    return out


def test_the_rule_catches_what_it_should():
    assert claims("SetuHQ discovered a new world.") and claims("Our pipeline confirmed the planet.")
    assert claims("The panel found a new planet here.")
    assert not claims("SetuHQ did not discover this planet.") and not claims("Every result is never a confirmed planet.")
    assert not claims("Found by transit in 2018.") and not claims("The TOI table lists it as CP.")


@pytest.fixture(scope="module")
def site(pi_men_app):
    return Path(pi_men_app).parent


def test_no_page_calls_setuhq_output_confirmed_or_discovered(site):
    bad = {}
    for p in json.loads((site / "assets" / "pages.json").read_text()):
        f = site / p.strip("/") / "index.html" if p != "/" else site / "index.html"
        if f.exists():
            found = claims(visible_text(f.read_text()))
            if found:
                bad[p] = found
    assert bad == {}
    assert "confirmed" not in VISITOR_TEXT  # the provenance note never says it either
    assert ATTRIBUTION == ("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. "
                           "Probes are deterministic matched-filter detectors.")


def test_no_stub_page_does_either(site):
    tpl = (site / "assets" / "stub-template.html").read_text()
    cat = json.loads((site / "assets" / "data" / "catalogue.json").read_text())
    P, rng = cat["planets"], random.Random(314)
    idx = rng.sample(range(len(P["name"])), 150)
    pages = [planet_page(tpl, cat, i)[1] for i in idx]
    stars = {}
    for i, s in enumerate(P["star"]):
        if s:
            stars.setdefault(s, []).append(i)
    for name in rng.sample(sorted(stars), 50):
        pages.append(star_page(tpl, cat, name, re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), stars[name])[1])
    assert len(pages) == 200
    bad = [c for p in pages for c in claims(visible_text(p))]
    assert bad == []
    assert all("{{" not in p and len(p.encode()) <= 4096 for p in pages)

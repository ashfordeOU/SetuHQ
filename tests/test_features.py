# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The v0.2 site features: the journey strip and the light-travel line (setuhq.journey), /explore/tess-now/
(setuhq.tessnow), /candidates/be-the-vetter/ (setuhq.vetter), /editions/ (setuhq.editions) and the figures'
Source / limits (setuhq.features). Every number from a stored file; nothing claims SetuHQ confirmed anything."""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

import pytest

from setuhq import editions, features, journey, tessnow, vetter
from setuhq.app import ROUTE_META, SUBNAV
from setuhq.names import ATTRIBUTION, DIP_STATE
from setuhq.routes import parse_path, url_for

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"\b(SetuHQ|this run|the panel|the pipeline|our|we)\b[^.]{0,60}\b(confirm(ed|s)?|discover(ed|y|s)?|new planet)\b", re.I)


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup)))


def _honest(text: str) -> None:
    for m in FORBIDDEN.finditer(text):
        assert re.search(r"\b(not|never|no|nothing)\b", m.group(0), re.I), m.group(0)
    assert "habitable" not in text.lower() and "superintelligence" not in text.lower()


# ---------- the journey strip ----------

ARCH = {"source": "NASA Exoplanet Archive (TAP)", "tics": [1],
        "toi": {"fetched_at": "2026-10-24T00:00:00+00:00", "rows": [
            {"toi": "9.01", "tid": "1", "pl_orbper": "5.0", "pl_tranmid": "2458000.0", "pl_orbpererr1": "0.0001",
             "pl_tranmiderr1": "0.001", "pl_trandurh": "2.0", "tfopwg_disp": "KP", "rowupdate": "2025-01-02 00:00:00"}]},
        "ps": {"fetched_at": "2026-10-24T00:00:00+00:00", "rows": [
            {"pl_name": "Star b", "tic_id": "TIC 1", "pl_orbper": "5.0", "pl_tranmid": "2458000.0", "tran_flag": "1",
             "disc_refname": "<a refstr=X href=https://example.org/x target=ref>Someone et al. 2020</a>"}]}}


def _dip(t, P=5.0, outcome="passed"):
    return {"candidate_id": "d", "outcome": outcome, "t_center": t, "time_unit": "BJD", "duration_hours": 2.0, "period_days": P}


def test_a_dip_on_a_known_planet_shows_others_records_dated():
    st = journey.steps(_dip(2458000.0 + 40 * 5.0), target="TIC 1", run_time="2026-10-21T00:00:00", probes_only=True, archive=ARCH)
    assert [s["label"] for s in st] == list(journey.LABELS)
    assert st[0]["asof"] == st[1]["asof"] == st[2]["asof"] == "2026-10-21"
    assert st[2]["text"] == "Probes only" and st[3]["text"] == "yes: TOI 9.01" and st[3]["asof"] == "2026-10-24"
    assert "KP" in st[4]["text"] and st[5]["text"] == "yes: Star b (Someone et al. 2020)" and st[5]["href"] == "https://example.org/x"
    out = journey.strip_html(st, archive=ARCH)
    assert out.count("as of ") == 6 and "never SetuHQ results" in out
    _honest(_text(out))


def test_unknown_steps_are_hollow_and_a_rejected_dip_says_so():
    st = journey.steps(_dip(2458002.5, P=None, outcome="rejected"), target="TIC 1", run_time="2026-10-21", probes_only=False, archive=ARCH)
    assert st[1]["text"] == "rejected" and st[1]["state"] == "no" and st[2]["text"] == "Sentinels and Probes"
    assert st[3]["state"] == "no" and st[4] == {**st[4], "state": "open", "text": "not announced"}
    other = journey.steps(_dip(1.0), target="TIC 2", run_time="2026-10-21", probes_only=False, archive=ARCH)
    assert [s["state"] for s in other[3:]] == ["open"] * 3 and other[4]["text"] == "not announced"
    assert 'class="j-open"' in journey.strip_html(other, archive=ARCH)


def test_the_stored_archive_file_and_the_example_runs():
    arch = json.loads((ROOT / journey.ARCHIVE).read_text())
    assert arch["toi"]["fetched_at"] and arch["ps"]["fetched_at"] and {r["toi"] for r in arch["toi"]["rows"]} >= {"144.01", "236.01"}
    from setuhq.docket import docket_data

    d = docket_data(ROOT / "runs" / "tess-toi-236-s2", title="x")
    assert all("rejected" in d["journey"][c["candidate_id"]] for c in d["candidates"] if c["outcome"] == "rejected")
    assert all("yes: TOI-236" not in s for s in d["journey"].values()), "a false positive is never in the literature as a planet"


def test_light_travel_time():
    assert journey.light_years(18.37) == 60 and journey.light_years(234) == 760 and journey.light_years(None) is None
    assert journey.light_line(None, "x") == ""
    line = journey.light_line(18.37, "exoplanet.eu, fetched 2026-10-18")
    assert line == "The light in this dip left the star about 60 years ago (distance 18.37 pc, exoplanet.eu, fetched 2026-10-18)."
    assert journey.light_line(22.453, "s", what="this star").startswith("The light from this star left it about 73 years ago")


# ---------- Where TESS is now ----------

def test_the_saved_schedule_is_stamped_and_sourced():
    sch = tessnow.load()
    assert sch["saved"] and "tess.mit.edu" in sch["url"] and "not live telemetry" in sch["note"]
    for s in sch["sectors"]:
        assert s["start"] < s["end"] and s["page"].endswith(f"sector-{s['sector']}/")
        cams = tessnow.cameras(s)
        for k in range(4):  # each boresight lies in its own camera's field, and the next camera is about 24° away
            assert tessnow.in_field(*s[f"cam{k + 1}"][:2], cams)
        a, b = (tessnow._vec(*s[f"cam{k}"][:2]) for k in (1, 2))
        assert 20 < math.degrees(math.acos(sum(x * y for x, y in zip(a, b)))) < 28


def test_current_sector():
    S = [{"start": "2026-01-01", "end": "2026-02-01"}, {"start": "2026-02-01", "end": "2026-03-01"}]
    assert tessnow.current_index(S, "2026-02-10") == 1 and tessnow.current_index(S, "2025-01-01") == 0
    assert tessnow.current_index(S, "2027-01-01") == 1


# ---------- the pages ----------

@pytest.fixture(scope="module")
def data():
    from setuhq.app import app_data

    return app_data(ROOT / "runs" / "tess-pi-men-s1", title="SetuHQ", catalog_path=ROOT / "docs/discoveries/catalog.json",
                    extra_runs=[ROOT / "runs" / r for r in ("tess-wasp-126-s1", "tess-toi-270-s5", "tess-hd-15337-s4", "tess-toi-236-s2")])


def test_tess_now_page(data):
    out = tessnow.section(data)
    t = _text(out)
    assert "Pointing from the published schedule, not live telemetry" in t and "Schedule saved on" in t
    assert 'id="tnrange"' in out and out.count('class="tnsec') == len(tessnow.load()["sectors"]) and out.count('class="tnsec on"') == 1
    assert "Model from stored values" in t and "Source:" in t
    _honest(t)


def test_be_the_vetter_page(data):
    out = vetter.section(data)
    t = _text(out)
    assert "A learning exercise, not a contribution to the science" in t and "not collected" in t
    outs = re.findall(r'data-out="(\w+)"', out)
    assert 2 <= len(outs) <= vetter.MAX_DIPS and {"passed", "flagged", "rejected"} <= set(outs)
    for card in out.split('<article class="card vtcard"')[1:]:
        o = re.search(r'data-out="(\w+)"', card).group(1)
        assert f"Vetting: {DIP_STATE[o][2]}." in _text(card)
        before = _text(card.split('<details class="vtreveal">')[0])
        assert DIP_STATE[o][2] not in before and "Real data, cited" in before
    assert ATTRIBUTION in t
    _honest(t)


def test_editions_page():
    out = editions.section()
    t = _text(out)
    for row in editions.ROWS:
        assert f">{row}<" in out
    assert not re.search(r"[$€£]\s?\d|\bper (month|year|seat)\b|\bpric(e|ing):", t, re.I), "no prices anywhere"
    assert "There are no prices on this site" in t and t.count(editions.CONTACT) >= 3 and 'data-copy="contact@ashforde.org"' in out
    assert "Available under contract" in t and "Request an evaluation" in t and "in development" in t
    assert not re.search(r"Pro is (live|available now)", t)
    assert "AGPL-3.0" in t and "commercial licence from Ashforde OÜ" in t
    assert "CC BY-NC 3.0 IGO" in t and "never part of SetuHQ Pro or of the commercial licence" in t
    _honest(t)


def test_routes_and_navigation():
    for route, path, nav in (("tessnow", "/explore/tess-now/", "explore"), ("vetter", "/candidates/be-the-vetter/", "candidates"),
                             ("editions", "/editions/", "docs")):
        assert url_for(route) == path and parse_path(path)["route"] == route
        assert ROUTE_META[route]["nav"] == nav and any(route in rs for _, _, rs in SUBNAV[nav])


def test_every_label_has_its_limits_and_the_hints_are_kept_safely():
    assert set(features.LIMITS) == {"real data, cited", "model from stored values", "artist's impression", "illustration", "speculative model"}
    js = features.SHELL_JS
    assert "SetuUI.limits" in js and "Source / limits" in js and "<details" in js
    assert js.count("localStorage") == 2 and js.count("try {") >= 2, "storage in try/catch"
    assert "Escape" in js

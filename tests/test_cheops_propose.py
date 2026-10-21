# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The CHEOPS proposal preparation pack: calendar and deadline arithmetic, orbit limits, RTL matching, the
anonymity lint, the planning estimates, the pack itself and the MCP tool's write safety. Offline.

Fixtures (tests/fixtures/cheops_propose/): ``rtl_synthetic.csv`` and ``call_page.html`` are synthetic, written in
the format of ESA's RTL CSV and call page (ESA's own RTL file is not redistributed: the code downloads it at run
time). ``simbad_*.json``, ``mast_TOI_1987.json`` and ``dace_wasp18_cone.json`` are public query answers recorded on
21 October 2026 and trimmed (identifier lists shortened; PI fields removed from the DACE answer).
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from setuhq.propose import draft, evidence, pack, planning, rules, sources, targets

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "cheops_propose"
UTC = timezone.utc


# ---------------------------------------------------------------- an offline fetcher


def fixture_answer(url: str, data: dict | None) -> bytes:
    if "cheops-running-call" in url:
        return (FIX / "call_page.html").read_bytes()
    if "RTL_" in url:
        return (FIX / "rtl_synthetic.csv").read_bytes()
    if "sim-tap" in url:
        q = (data or {}).get("query", "")
        for key, f in (("'AU Mic'", "simbad_AU_Mic.json"), ("'HD 197481'", "simbad_AU_Mic.json"),
                       ("'TOI-1987'", "simbad_TOI_1987.json")):
            if key in q:
                return (FIX / f).read_bytes()
        return b'{"data": []}'
    if "mast.stsci.edu" in url:
        if "TOI-1987" in (data or {}).get("request", ""):
            return (FIX / "mast_TOI_1987.json").read_bytes()
        return b'{"resolvedCoordinate": []}'
    if "cheops-webapp" in url:
        return (FIX / "dace_wasp18_cone.json").read_bytes() if "24.354" in url else b""
    if "exoplanetarchive" in url:
        return b"[]"
    raise AssertionError(f"unexpected request {url}")


class FixtureFetcher(sources.Fetcher):
    def _request(self, full, data):
        self.requests = getattr(self, "requests", []) + [full]
        return sources.Fetched(full, fixture_answer(full, data), "2026-10-21T12:00:00+00:00")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any request that is not served from fixtures fails the test."""
    monkeypatch.setattr(sources.Fetcher, "_request", lambda self, full, data: sources.Fetched(
        full, fixture_answer(full, data), "2026-10-21T12:00:00+00:00"))


def paris(y, mo, d, h, mi):
    return rules.paris_local(y, mo, d, h, mi)


# ---------------------------------------------------------------- deadlines, cycles, DST


def test_deadline_is_2359_paris_on_the_last_day_with_the_right_offset():
    oct26 = rules.deadline(2026, 10)  # summer time ends 25 Oct 2026: the deadline is CET
    assert (oct26.day, oct26.hour, oct26.minute, rules.zone_name(oct26)) == (31, 23, 59, "CET")
    assert oct26.astimezone(UTC) == datetime(2026, 10, 31, 22, 59, tzinfo=UTC)
    mar27 = rules.deadline(2027, 3)  # summer time starts 28 Mar 2027: CEST
    assert rules.zone_name(mar27) == "CEST" and mar27.astimezone(UTC) == datetime(2027, 3, 31, 21, 59, tzinfo=UTC)
    assert rules.deadline(2028, 2).day == 29 and rules.deadline(2027, 2).day == 28  # leap year
    assert rules.deadline(2027, 4).day == 30 and rules.zone_name(rules.deadline(2027, 4)) == "CEST"
    assert rules.deadline(2026, 12).day == 31 and rules.zone_name(rules.deadline(2026, 12)) == "CET"


def test_the_eu_rule_fallback_agrees_with_the_tz_database(monkeypatch):
    with_tz = {(y, m): rules.deadline(y, m).astimezone(UTC) for y in (2026, 2027, 2028, 2029) for m in range(1, 13)}
    monkeypatch.setattr(rules, "_paris", lambda: None)
    for (y, m), t in with_tz.items():
        assert rules.deadline(y, m).astimezone(UTC) == t, (y, m)
    # the switch instants themselves
    assert rules.eu_summer_time(datetime(2026, 3, 29, 1, 0, tzinfo=UTC))
    assert not rules.eu_summer_time(datetime(2026, 3, 29, 0, 59, tzinfo=UTC))
    assert not rules.eu_summer_time(datetime(2026, 10, 25, 1, 0, tzinfo=UTC))
    assert rules.eu_summer_time(datetime(2026, 10, 25, 0, 59, tzinfo=UTC))


def test_current_cycle_rolls_over_at_the_deadline_in_paris_time():
    assert rules.current_cycle(paris(2026, 10, 31, 23, 58)) == (2026, 10)
    assert rules.current_cycle(paris(2026, 10, 31, 23, 59)) == (2026, 11)  # the deadline minute counts as late
    # 23:30 UTC on 31 October is already 1 November in Paris
    assert rules.current_cycle(datetime(2026, 10, 31, 23, 30, tzinfo=UTC)) == (2026, 11)
    # 22:30 UTC on 30 April 2027 is 00:30 CEST on 1 May
    assert rules.current_cycle(datetime(2027, 4, 30, 22, 30, tzinfo=UTC)) == (2027, 5)
    assert rules.current_cycle(datetime(2027, 4, 30, 21, 30, tzinfo=UTC)) == (2027, 4)


def test_next_cycle_by_programme_type():
    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    assert rules.next_cycle(now, "regular") == (2026, 10)
    assert rules.next_cycle(now, "large") == (2026, 10)
    assert rules.next_cycle(now, "fasttrack") == (2026, 10)
    later = datetime(2026, 11, 5, tzinfo=UTC)
    assert rules.next_cycle(later, "regular") == (2026, 11)
    assert rules.next_cycle(later, "large") == (2027, 4)
    assert rules.next_cycle(datetime(2027, 4, 30, 21, 58, tzinfo=UTC), "large") == (2027, 4)
    assert rules.next_cycle(datetime(2027, 4, 30, 22, 0, tzinfo=UTC), "large") == (2027, 10)
    assert rules.next_cycle(datetime(2029, 11, 1, tzinfo=UTC), "large") is None
    assert rules.next_cycle(datetime(2029, 12, 31, 23, tzinfo=UTC), "regular") is None


def test_cycle_info_timeline_and_rules():
    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    c = rules.cycle_info(2026, 11, "regular", now)
    assert c["errors"] == [] and c["earliest_start"] == "2027-02-01" and c["nominal_start_month"] == "2027-03"
    assert c["about_three_months_after_close"] == "2027-02-28"  # 30 Nov + 3 months, clamped to February
    assert c["outcome_expected"] == "last week of 2026-12" and "2027-05-30" in c["observable_by_note"]
    assert rules.cycle_info(2026, 10, "regular", now)["earliest_start"] == "2027-01-01"
    assert "no TAC" in rules.cycle_info(2026, 11, "fasttrack", now)["tac"]
    assert any("April and October" in e for e in rules.cycle_info(2027, 5, "large", now)["errors"])
    assert rules.cycle_info(2027, 4, "large", now)["errors"] == []
    assert rules.cycle_info(2028, 10, "large", now)["errors"] == []
    old = rules.cycle_info(2026, 8, "regular", now)
    assert any("has passed" in e for e in old["errors"]) and any("31 December 2026" in w for w in old["warnings"])
    assert any("before the Running Call" in e for e in rules.cycle_info(2026, 6, "regular", now)["errors"])
    assert any("September 2029" in w for w in rules.cycle_info(2029, 10, "large", now)["warnings"])
    assert any("after the Running Call" in e for e in rules.cycle_info(2030, 1, "regular", now)["errors"])
    with pytest.raises(ValueError):
        rules.parse_cycle("2026-13")
    with pytest.raises(ValueError):
        rules.parse_cycle("Oct 2026")


def test_window_inside_the_observing_period():
    assert rules.check_window(date(2027, 1, 1), date(2029, 12, 31))["errors"] == []
    assert rules.check_window(date(2026, 9, 1), date(2027, 1, 1))["errors"]
    assert rules.check_window(date(2027, 1, 1), date(2030, 1, 1))["errors"]
    assert rules.check_window(date(2026, 12, 1), date(2027, 6, 1), date(2027, 1, 1))["warnings"]


# ---------------------------------------------------------------- orbit limits


@pytest.mark.parametrize("prog,orbits,ok,warn", [
    ("regular", 1, True, False), ("regular", 120, True, False), ("regular", 121, False, False),
    ("regular", 0, False, False), ("large", 120, False, False), ("large", 121, True, False),
    ("large", 500, True, False), ("large", 501, False, False), ("fasttrack", 25, True, False),
    ("fasttrack", 26, True, True), ("fasttrack", 50, True, True), ("fasttrack", 51, False, False),
])
def test_orbit_limits(prog, orbits, ok, warn):
    r = rules.check_orbits(orbits, prog)
    assert (not r["errors"]) is ok
    assert bool(r["warnings"]) is warn


def test_orbit_limit_messages_point_to_the_right_type():
    assert "Large programme" in rules.check_orbits(200, "regular")["errors"][0]
    assert "Regular programme" in rules.check_orbits(60, "large")["errors"][0]
    assert rules.check_orbits(None, "regular")["errors"] == []
    assert any("HST or JWST" in h for h in rules.check_orbits(10, "fasttrack")["hints"])
    assert rules.check_visit(3) and rules.check_visit(5) == [] and rules.check_visit(101)
    with pytest.raises(ValueError):
        rules.programme("medium")


# ---------------------------------------------------------------- the RTL


def rtl_entries():
    return sources.parse_rtl_csv((FIX / "rtl_synthetic.csv").read_bytes(), "rtl_synthetic.csv")[1]


def test_rtl_csv_parses_decimal_commas_bom_and_quoted_notes():
    title, entries = sources.parse_rtl_csv((FIX / "rtl_synthetic.csv").read_bytes(), "x")
    assert title.startswith("Synthetic test list")
    assert [e.name for e in entries] == ["AU Mic", "Synthetic-1", "TOI-396", "AlphaCenB"]
    assert entries[0].ra == pytest.approx(311.2897) and entries[0].dec == pytest.approx(-31.3409)
    assert entries[3].notes == "a note; with a semicolon" and entries[0].gaia_id is None


def test_rtl_links_are_found_and_deduplicated():
    links = sources.rtl_links((FIX / "call_page.html").read_text())
    assert [sources.rtl_file_name(u) for u, _ in links] == ["RTL_20270101_test.csv", "RTL_20260706_test.csv"]
    assert links[0][0].startswith("https://www.cosmos.esa.int/documents/")


def test_rtl_match_by_name_variants():
    e = rtl_entries()
    assert targets.match_rtl(e, name="Alpha Centauri B")["reserved"]
    assert targets.match_rtl(e, name="alpha cen b")["reserved"]
    assert targets.match_rtl(e, name="TOI 396")["reserved"]
    assert not targets.match_rtl(e, name="TOI-3960")["reserved"]


def test_rtl_match_by_simbad_alias():
    resolved = sources.parse_simbad((FIX / "simbad_AU_Mic.json").read_bytes(), "HD 197481")
    assert resolved.main_id == "HD 197481" and "V* AU Mic" in resolved.aliases
    m = targets.match_rtl(rtl_entries(), name="HD 197481", aliases=resolved.aliases)
    assert m["reserved"] and "alias" in m["matches"][0]["matched_by"]


def test_rtl_match_by_coordinates_within_a_radius():
    e = rtl_entries()
    ra, dec = 42.98436, -30.81452  # the TOI-396 entry
    off = 10.0 / 3600.0
    hit = targets.match_rtl(e, name="Some other name", ra=ra, dec=dec + off)
    assert hit["reserved"] and hit["matches"][0]["matched_by"][0].startswith("position")
    near = targets.match_rtl(e, name="Some other name", ra=ra, dec=dec + 60 / 3600.0)
    assert not near["reserved"] and near["nearby"][0]["rtl_name"] == "TOI-396"
    far = targets.match_rtl(e, name="Some other name", ra=ra, dec=dec + 1.0)
    assert not far["reserved"] and not far["nearby"]
    assert targets.separation_arcsec(10, 0, 10, 1 / 3600) == pytest.approx(1.0, rel=1e-6)


def test_coordinate_source_warnings():
    assert any("J2015.5" in w for w in targets.coordinate_warnings("ExoFOP"))
    assert any("J2015.5" in w for w in targets.coordinate_warnings("gaia"))
    assert targets.coordinate_warnings("simbad") == []
    # 1 arcsec/yr of proper motion in Dec: a J2015.5 position is 15.5" off the J2000 one
    w = targets.coordinate_warnings("other", 100.0, 10.0 + 15.5 / 3600, 100.0, 10.0, 0.0, 1000.0)
    assert any("looks like a J2015.5" in x for x in w)


# ---------------------------------------------------------------- the anonymity lint


@pytest.mark.parametrize("text,rule", [
    ("Contact jane.doe@example.org for the data.", "email"),
    ("This builds on our previous work on hot Jupiters.", "self-reference"),
    ("We have previously shown that the phase curve is asymmetric.", "self-reference"),
    ("In our paper we fitted the light curve.", "self-reference"),
    ("My group has developed a new detrending method.", "self-reference"),
    ("The analysis uses our own pipeline.", "self-reference"),
    ("We are the developers of the code.", "self-reference"),
    ("Data were reduced at the University of Somewhere.", "institution"),
    ("ORCID 0000-0002-1825-0097.", "orcid"),
    ("Discussed with Dr. Smith last year.", "title-and-name"),
    ("This work was funded by the national agency.", "funding"),
    ("Code at https://github.com/someone/thing.", "personal-url"),
])
def test_lint_flags_identifying_text(text, rule):
    found = draft.lint_text(text)
    assert any(f["rule"] == rule and f["level"] == "warn" for f in found), found


def test_lint_flags_given_author_names_and_passes_neutral_text():
    text = "Doe et al. (2026) have previously shown a 3-sigma secondary eclipse."
    assert any(f["rule"] == "author-name" for f in draft.lint_text(text, author_names=["Doe"]))
    assert [f for f in draft.lint_text(text) if f["level"] == "warn"] == []
    neutral = ("The transit was detected in TESS data (Ricker et al. 2015) and observed by CHEOPS "
               "(Benz et al. 2021). Previous work by others reported a period of 2.586 d.")
    assert [f for f in draft.lint_text(neutral) if f["level"] == "warn"] == []


def test_lint_checks_file_names(tmp_path):
    f = tmp_path / "proposal_JDoe_jane.doe@example.org.md"
    f.write_text("clean text")
    found = draft.lint_files([f], author_names=["J Doe"])
    assert {x["rule"] for x in found} == {"file-name"}
    assert draft.lint_filenames([tmp_path / "scientific-justification.md"], author_names=["Doe"]) == []


# ---------------------------------------------------------------- planning estimates


def test_precision_model_reproduces_its_anchors():
    assert planning.sigma_1h(8.97) / 6 ** 0.5 == pytest.approx(12.8)
    assert planning.sigma_1h(12.0) / 3 ** 0.5 == pytest.approx(120.0)
    assert planning.sigma_1h(12.0, "optimistic") / 3 ** 0.5 == pytest.approx(85.0)
    # the paper's ETC example (G = 9: 13 ppm in 6 h) lies within 5 percent
    assert planning.sigma_1h(9.0) / 6 ** 0.5 == pytest.approx(13.0, rel=0.05)
    p = planning.precision(10.0, 0.5)
    c = p["cases"]["conservative"]
    assert c["ppm_per_orbit"] == pytest.approx(c["ppm_1h"] / (98.7 / 60 * 0.5) ** 0.5)
    assert "Fortier" in p["reference"] and "ESTIMATE" in p["label"] and "Exposure Time Calculator" in p["confirm"]
    assert "warning" in planning.precision(13.5) and "warning" not in planning.precision(10.0)
    assert planning.precision(None)["available"] is False


def test_orbits_needed_scales_with_snr_and_respects_the_visit_minimum():
    a = planning.orbits_needed(gmag=10, depth_ppm=300, duration_hours=2, target_snr=10)
    b = planning.orbits_needed(gmag=10, depth_ppm=300, duration_hours=2, target_snr=20)
    assert b["events_needed"] >= 3 * a["events_needed"]
    assert a["orbits_per_visit"] >= 5 and a["orbits_total"] == a["events_needed"] * a["orbits_per_visit"]
    deep = planning.orbits_needed(gmag=10, depth_ppm=5000, duration_hours=2, target_snr=10)
    assert deep["events_needed"] == 1 and deep["visit_minimum_applied"]
    padded = planning.orbits_needed(gmag=10, depth_ppm=300, duration_hours=2, target_snr=10, ephemeris_sigma_hours=2)
    assert padded["orbits_per_visit"] > a["orbits_per_visit"]
    fl = planning.orbits_needed(gmag=10, depth_ppm=2000, duration_hours=0.2, target_snr=5, event="flare",
                                flare_rate_per_day=0.5, n_flares=2)
    assert fl["orbits_total"] == pytest.approx(4 * 24 / (98.7 / 60 * 0.7), abs=1)


def test_ephemeris_uncertainty_grows_through_the_window():
    e = planning.ephemeris_in_window(t0=2459283.07354, t0_err=0.000344, period=2.5861562, period_err=0.000002,
                                     start_jd=2461406.5, end_jd=2462501.5, source="test")
    n = round((2461406.5 - 2459283.07354) / 2.5861562)
    assert e["window_start"]["sigma_hours"] == pytest.approx(24 * (0.000344 ** 2 + (n * 2e-6) ** 2) ** 0.5, rel=1e-6)
    assert e["window_end"]["sigma_hours"] > e["window_start"]["sigma_hours"]
    assert e["transits_in_window"] == pytest.approx((2462501.5 - 2461406.5) / 2.5861562, abs=1)
    assert "warning" in planning.ephemeris_in_window(t0=1000.0, t0_err=None, period=2.0, period_err=None,
                                                     start_jd=2461406.5, end_jd=2461500.5, source="x")


def test_sun_screen_uses_the_117_degree_constraint():
    near_pole = planning.sun_screen(84.2912, -80.4691)  # pi Men, ecliptic latitude about -76
    assert near_pole["can_meet_sun_constraint"] is False and "very likely not observable" in near_pole["statement"]
    ecliptic = planning.sun_screen(185.332, -14.062)
    assert ecliptic["can_meet_sun_constraint"] and "NOT a visibility result" in ecliptic["statement"]


# ---------------------------------------------------------------- evidence


def test_noise_per_timescale_on_white_noise():
    import numpy as np

    rng = np.random.default_rng(1)
    t = np.arange(0, 20, 10 / 1440)
    f = 1 + rng.normal(0, 500e-6, t.size)
    n = evidence.noise_per_timescale(t.tolist(), f.tolist())
    per_bin_1h = 500 / 6 ** 0.5
    assert n["1h"] == pytest.approx(per_bin_1h, rel=0.2)
    assert n["6h"] == pytest.approx(500 / 36 ** 0.5, rel=0.35)


def test_stored_evidence_for_pi_men_reads_the_run():
    ev = evidence.stored_evidence(ROOT, tic=261136679, names=["pi Men"])
    assert ev["found"] and ev["runs"][0]["run"] == "runs/tess-pi-men-s1"
    assert ev["runs"][0]["noise"] and ev["runs"][0]["noise"][0]["1h"] > 0
    eph = evidence.best_ephemeris(ev)
    assert eph["period"] == pytest.approx(6.27, abs=0.01) and eph["t0_err"] and "candidate" in eph["source"]
    assert "not confirmations" in ev["label"]


def test_stellar_hooks_degrade_gracefully(monkeypatch, tmp_path):
    import sys
    import types

    broken = types.ModuleType("setuhq.flares")
    broken.proposal_evidence = lambda *a, **k: 1 / 0
    monkeypatch.setitem(sys.modules, "setuhq.flares", broken)
    monkeypatch.setitem(sys.modules, "setuhq.pulsations", types.ModuleType("setuhq.pulsations"))
    good = types.ModuleType("setuhq.cheops")
    good.proposal_evidence = lambda target, *, tic, root: {"n_flares": 2, "target": target}
    monkeypatch.setitem(sys.modules, "setuhq.cheops", good)
    h = evidence.stellar_hooks("X", tic=1, root=tmp_path)
    assert h["flares"]["status"].startswith("hook failed")
    assert h["pulsations"]["status"] == "installed, no proposal_evidence hook"
    assert h["cheops_ingest"]["evidence"] == {"n_flares": 2, "target": "X"}


# ---------------------------------------------------------------- sources


def test_fetcher_caches_per_day_and_never_reaches_out_offline(tmp_path):
    f = FixtureFetcher(cache_dir=tmp_path)
    a = f.get(sources.CALL_PAGE, suffix=".html")
    b = FixtureFetcher(cache_dir=tmp_path).get(sources.CALL_PAGE, suffix=".html")
    assert b.cached and b.sha256 == a.sha256
    with pytest.raises(sources.SourceError):
        sources.Fetcher(cache_dir=None, offline=True).get(sources.CALL_PAGE)
    rtl = FixtureFetcher(cache_dir=tmp_path).get("https://x/RTL_20270101_v2.csv/abc", cache_name="RTL_20270101_v2.csv")
    assert any(p.name.startswith("RTL_20270101_v2__fetched-") for p in tmp_path.iterdir()) and rtl.body


def test_dace_parsing_keeps_public_metadata_only():
    visits = sources.parse_dace_visits((FIX / "dace_wasp18_cone.json").read_bytes())
    assert visits and all("visit_id" in v and "file_key" in v for v in visits)
    assert not any("pi_name" in v or "pi_uid" in v for v in visits)
    assert sources.parse_dace_visits(b"") == []


# ---------------------------------------------------------------- the pack


def build(tmp_path, target="TOI-1987", **kw):
    return pack.build_pack(target, tmp_path / "pack", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                           fetcher=FixtureFetcher(cache_dir=None), **kw)


def test_pack_for_a_public_unreserved_toi_host(tmp_path):
    p = build(tmp_path, orbits=30, author_names=["Jane Doe"])
    out = tmp_path / "pack"
    names = sorted(x.name for x in out.iterdir())
    assert names == ["README.md", "anonymity-lint.txt", "checklist.md", "pack.json", "scientific-justification.md",
                     "sources", "technical-justification.md"]
    assert p["cycle"]["cycle"] == "2026-10" and p["cycle"]["deadline_zone"] == "CET"
    assert p["target"]["coord_source"] == "SIMBAD" and p["target"]["tic"] == 349088467
    assert p["status"]["rtl"]["checked"] and not p["status"]["rtl"]["reserved"]
    assert p["status"]["archive"]["checked"] and not p["status"]["archive"]["already_observed"]
    assert p["evidence"]["catalogue"] and "not a confirmation" in " ".join(p["evidence"]["summary"])
    assert [f for f in p["anonymity_lint"] if f["level"] == "warn"] == []
    readme = (out / "README.md").read_text()
    assert draft.DISCLAIMER in readme and "Confirm with ESA's Exposure Time Calculator" in readme
    checklist = (out / "checklist.md").read_text()
    import re

    heads = re.findall(r"^## (\d)\. (.+)$", checklist, re.M)
    assert [n for n, _ in heads] == list("1234567")
    order = ["Registration", "Coordinates", "Visibility", "Target status", "Exposure time", "templates", "PHT1"]
    assert all(word in title for word, (_, title) in zip(order, heads))
    for link in (draft.LINKS["pht1"], draft.LINKS["etc"], draft.LINKS["target_checker"], draft.LINKS["registration"]):
        assert link in checklist
    all_text = " ".join(f.read_text() for f in out.glob("*.md")) + (out / "pack.json").read_text()
    assert "Jane Doe" not in all_text
    low = all_text.lower()
    for claim in ("confirmed planet", "discovered", "feasible observation", "is visible to cheops", "approved by esa"):
        assert claim not in low, claim
    data = json.loads((out / "pack.json").read_text())
    assert all(s.get("sha256") and s.get("url") and s.get("fetched_at") for s in data["sources"])
    assert data["acknowledgement"]["text"].startswith("CHEOPS is an ESA mission in partnership with Switzerland")


def test_pack_flags_reserved_and_already_observed_targets(tmp_path):
    p = build(tmp_path, target="HD 197481")
    assert p["status"]["rtl"]["reserved"]
    q = pack.build_pack("Synthetic star", tmp_path / "p2", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=FixtureFetcher(cache_dir=None), ra=24.354305, dec=-45.67788, coord_source="simbad")
    arch = q["status"]["archive"]
    assert arch["already_observed"] and arch["public_visits"][0]["visit_id"] and arch["programme_ids"]
    text = (tmp_path / "p2" / "README.md").read_text()
    assert "already observed" in text and "visit ids" in text and arch["programme_ids"][0] in text
    assert "pi_name" not in (tmp_path / "p2" / "pack.json").read_text()


def test_pack_replaces_exofop_coordinates_and_says_so(tmp_path):
    p = build(tmp_path, ra=185.3321, dec=-14.0623, coord_source="exofop")
    assert "replaced" in p["target"]["coord_source"] and p["target"]["ra"] == pytest.approx(185.33198001579)
    assert any("J2015.5" in w for w in p["target"]["coord_warnings"])


def test_pack_offline_says_not_checked(tmp_path):
    p = pack.build_pack("TOI-1987", tmp_path / "pack", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=sources.Fetcher(cache_dir=None, offline=True), gmag=10.07, use_toi_table=False)
    assert not p["status"]["rtl"]["checked"] and not p["status"]["archive"]["checked"]
    assert "not checked" in (tmp_path / "pack" / "README.md").read_text()


def test_pack_refuses_an_existing_directory_and_a_bad_cycle(tmp_path):
    (tmp_path / "pack").mkdir()
    with pytest.raises(FileExistsError):
        build(tmp_path)
    with pytest.raises(ValueError):
        build(tmp_path, cycle="2026-13")


def test_large_programme_out_of_cycle_is_an_error_in_the_pack(tmp_path):
    p = build(tmp_path, programme="large", orbits=200, cycle="2027-05")
    assert any("April and October" in e for e in p["cycle"]["errors"])
    assert "ERROR" in (tmp_path / "pack" / "README.md").read_text()


# ---------------------------------------------------------------- the CLI


def test_cli_writes_a_pack_and_lints(tmp_path, capsys, monkeypatch):
    from setuhq.cli import main

    monkeypatch.setenv("SETUHQ_ROOT", str(ROOT))
    out = tmp_path / "p"
    code = main(["propose", "cheops", "TOI-1987", "--orbits", "20", "--today", "2026-10-21", "--out", str(out),
                 "--no-cache"])
    captured = capsys.readouterr()
    assert code == 0 and (out / "pack.json").exists()
    assert "not affiliated with" in captured.err and "nothing was submitted" in captured.out
    assert main(["propose", "cheops", "TOI-1987", "--out", str(out), "--no-cache"]) == 2  # never overwrites
    bad = tmp_path / "draft.md"
    bad.write_text("As shown in our previous work (jane@example.org).")
    assert main(["propose", "lint", str(bad)]) == 1
    assert main(["propose", "lint", str(out / "scientific-justification.md")]) == 0


# ---------------------------------------------------------------- the MCP tool's write safety


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    return tmp_path


def _tree(base: Path) -> set[str]:
    return {str(p.relative_to(base)) for p in base.rglob("*")}


def test_mcp_tool_writes_only_a_new_runs_propose_directory(data_root):
    from setuhq import tools

    before = _tree(data_root)
    env = tools.cheops_proposal_pack("TOI-1987", "first")
    assert env["tool"] == "cheops_proposal_pack" and env["result"]["pack_dir"] == "runs/propose/first"
    assert any("not affiliated with" in h for h in env["honesty"])
    new = _tree(data_root) - before
    assert new and all(p == "runs" or p.startswith("runs/propose") for p in new)  # no cache, nothing else
    json.dumps(env, allow_nan=False)
    with pytest.raises(tools.ToolError, match="already exists"):
        tools.cheops_proposal_pack("TOI-1987", "first")


@pytest.mark.parametrize("name", ["../escape", "a/b", "", ".hidden", "x" * 80, "/abs"])
def test_mcp_tool_refuses_names_that_are_paths(data_root, name):
    from setuhq import tools

    with pytest.raises(tools.ToolError):
        tools.cheops_proposal_pack("TOI-1987", name)
    assert not (data_root / "runs" / "propose").exists() or not any((data_root / "runs" / "propose").iterdir())


def test_mcp_tool_never_follows_a_link(data_root, tmp_path_factory):
    from setuhq import tools

    elsewhere = tmp_path_factory.mktemp("elsewhere")
    (data_root / "runs").mkdir()
    os.symlink(elsewhere, data_root / "runs" / "propose")
    with pytest.raises(tools.ToolError, match="link"):
        tools.cheops_proposal_pack("TOI-1987", "x")
    assert not any(elsewhere.iterdir())


def test_mcp_tool_bad_arguments_leave_nothing_behind(data_root):
    from setuhq import tools

    with pytest.raises(tools.ToolError):
        tools.cheops_proposal_pack("TOI-1987", "y", programme="medium")
    with pytest.raises(tools.ToolError):
        tools.cheops_proposal_pack("TOI-1987", "z", cycle="2026-13")
    assert not (data_root / "runs" / "propose" / "y").exists() and not (data_root / "runs" / "propose" / "z").exists()


def test_mcp_server_marks_the_tool_as_a_write_and_hides_it_over_plain_http():
    pytest.importorskip("mcp")
    import anyio

    from setuhq.mcp_server import build_server

    def names(server):
        return {t.name: t for t in anyio.run(server.list_tools)}

    full = names(build_server())
    ann = full["cheops_proposal_pack"].annotations
    read_only = ann.read_only_hint if hasattr(ann, "read_only_hint") else ann.readOnlyHint
    assert read_only is False
    assert "cheops_proposal_pack" not in names(build_server(allow_writes=False))

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The CHEOPS proposal preparation pack: calendar and deadline arithmetic, orbit limits, RTL matching, the
anonymity lint, the planning estimates, the pack itself and the MCP tool's write safety. Offline.

Fixtures (tests/fixtures/cheops_propose/):

* ``rtl_synthetic.csv`` is mixed: public target names with synthetic rows (coordinates, notes, title) in the format
  of ESA's RTL CSV. ESA's own RTL file is not redistributed; the code downloads it at run time.
* ``call_page.html`` is synthetic, in the format of the Running Call page's RTL links.
* ``simbad_*.json`` and ``mast_TOI_1987.json`` are public answers recorded on 21 October 2026 (identifier lists
  shortened).
* ``dace_wasp18_cone.json`` is a DACE answer recorded on 21 October 2026 with its real column set, including the PI
  columns, whose values were replaced by fakes (``FAKEPI-*``, 9000xx); one visit was set to not public. The code must
  never store those columns: the tests check every file it writes.
* ``lint/`` and ``lint/review15/`` hold two independent reviews' bypass cases for the anonymity lint (text files
  and PDFs: page text, metadata, an image, outlined text, a caption pypdf's layout extraction drops).
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
        import urllib.parse

        if "24.354" in url or '"WASP-18"' in urllib.parse.unquote_plus(url):
            return (FIX / "dace_wasp18_cone.json").read_bytes()
        raise sources.NotFound(f"{url}: HTTP 404")  # DACE's answer to an empty search
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
    assert any(f["rule"].startswith("author-name") for f in draft.lint_text(text, author_names=["Doe"]))
    assert [f for f in draft.lint_text(text) if f["level"] == "warn"] == []
    neutral = ("The transit was detected in TESS data (Ricker et al. 2015) and observed by CHEOPS "
               "(Benz et al. 2021). Previous work by others reported a period of 2.586 d.")
    assert [f for f in draft.lint_text(neutral) if f["level"] == "warn"] == []


def test_lint_checks_file_names(tmp_path):
    f = tmp_path / "proposal_JDoe_jane.doe@example.org.md"
    f.write_text("clean text")
    found = draft.lint_files([f], author_names=["J Doe"])
    assert {x["rule"].split(" ")[0] for x in found} == {"file-name"}
    assert draft.lint_filenames([tmp_path / "scientific-justification.md"], author_names=["Doe"]) == []
    assert draft.lint_filenames([tmp_path / "0000-0002-1825-0097.md"])
    assert draft.lint_filenames([tmp_path / "TOI-1987-technical.md"]) == []


# The bypass cases an independent review found (tests/fixtures/cheops_propose/lint/).
LINT = FIX / "lint"


def _warn_lines(findings):
    return {f["line"] for f in findings if f["level"] == "warn"}


def test_lint_catches_every_review_case():
    text = (LINT / "cases.txt").read_text()
    found = draft.lint_text(text, author_names=["Jane Doe"])
    lines = _warn_lines(found)
    n = len(text.splitlines())
    assert {1, 2} & lines  # "In our previous / work": a phrase wrapped over two lines
    assert set(range(3, n + 1)) <= lines, sorted(set(range(3, n + 1)) - lines)
    # and without any name given, every case except the bare name forms is still caught
    no_names = _warn_lines(draft.lint_text(text))
    assert set(range(3, n + 1)) - {11} <= no_names, sorted(set(range(3, n + 1)) - {11} - no_names)


@pytest.mark.parametrize("text,rule", [
    ("My previous paper measured the radius.", "self-reference"),
    ("Our earlier CHEOPS programme observed it.", "self-reference"),
    ("Our 2023 study found a second planet.", "self-reference"),
    ("This builds on our work (Doe et al. 2023).", "self-reference"),
    ("We are the team that discovered TOI-1987 b.", "self-reference"),
    ("Contact: jane.doe [at] unige.ch", "email-obfuscated"),
    ("Contact: jane.doe at unige.ch", "email-obfuscated"),
    ("Data reduced at the university of geneva.", "institution"),
    ("The ETH Zurich and Harvard teams lead this.", "institution"),
])
def test_lint_review_phrasings(text, rule):
    assert any(f["rule"] == rule and f["level"] == "warn" for f in draft.lint_text(text)), draft.lint_text(text)


def test_lint_author_name_variants():
    for text in ("J. Doe measured it.", "DOE, J. et al. 2023", "as in Doe et al. (2023)", "Doe (2023) found",
                 "Jane Doe's group", "see (Doe 2023)"):
        assert any(f["rule"].startswith("author-name") for f in draft.lint_text(text, author_names=["Jane Doe"])), text
    assert not any(f["rule"].startswith("author-name")
                   for f in draft.lint_text("The doe-eyed star.", author_names=["Jane Doe"]))


def test_lint_lets_official_tool_urls_through_but_not_the_institution():
    assert not draft.lint_text("Checked with https://cheops.unige.ch/pht2/search-reserved-targets/ today.")
    assert any(f["rule"] == "institution" for f in draft.lint_text("Our colleagues at UniGE helped."))
    assert any(f["rule"] == "institution" for f in draft.lint_text("See https://www.unige.ch/~someone/ for code."))


def test_lint_user_institutions_are_case_insensitive():
    found = draft.lint_text("Observed from the STARLAB facility.", institutions=["Starlab"])
    assert any(f["rule"] == "institution" for f in found)


def test_lint_wrapped_lines_are_joined():
    found = draft.lint_text((LINT / "wrap.txt").read_text())
    assert {1, 3} <= _warn_lines(found)


def test_lint_review_file_names():
    names = [LINT / "Doe_SJ.md", LINT / "jdoe.md", LINT / "UniGE-technical.md"]
    found = draft.lint_filenames(names, author_names=["Jane Doe"])
    assert {f["file"] for f in found} == {p.name for p in names}
    assert {f["file"] for f in draft.lint_filenames(names)} >= {"Doe_SJ.md", "UniGE-technical.md"}


def test_lint_never_reports_a_pdf_or_binary_as_clean(tmp_path, monkeypatch):
    pdf = LINT / "sj.pdf"
    try:
        found = draft.lint_files([pdf], author_names=["Jane Doe"])
    except draft.LintInputError:
        pass
    else:
        assert {"self-reference", "email", "institution"} <= {f["rule"] for f in found if f["level"] == "warn"}
    import builtins

    real_import = builtins.__import__

    def no_pypdf(name, *a, **k):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pypdf)
    with pytest.raises(draft.LintInputError, match="pypdf"):
        draft.lint_files([pdf])
    blob = tmp_path / "x.docx"
    blob.write_bytes(b"PK\x03\x04\x00\x00binary")
    with pytest.raises(draft.LintInputError):
        draft.lint_files([blob])


def test_lint_cli_exit_codes_and_wording(tmp_path, capsys):
    from setuhq.cli import main

    assert main(["propose", "lint", str(LINT / "sj.pdf"), "--author-name", "Jane Doe"]) in (1, 2)
    blob = tmp_path / "x.bin"
    blob.write_bytes(b"\x00\x01\x02")
    assert main(["propose", "lint", str(blob)]) == 2
    assert "not a text file" in capsys.readouterr().err
    clean = tmp_path / "clean.md"
    clean.write_text("A neutral sentence about a transiting planet.")
    assert main(["propose", "lint", str(clean)]) == 0
    assert "cannot guarantee anonymity" in capsys.readouterr().out


# ---------------------------------------------------------------- planning estimates


def test_precision_model_reproduces_its_anchors():
    assert planning.sigma_1h(8.97) / 6 ** 0.5 == pytest.approx(12.8)
    assert planning.sigma_1h(12.0) / 3 ** 0.5 == pytest.approx(128.0)
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


FAKE_PI = ("pi_name", "pi_uid", "FAKEPI", "Fakefirst", "900001", "900002")


def test_the_dace_fixture_has_the_real_columns():
    raw = (FIX / "dace_wasp18_cone.json").read_text()
    assert '"pi_name"' in raw and '"pi_uid"' in raw and "FAKEPI-ALPHA" in raw  # the fixture must not hide reality


def test_dace_answers_are_filtered_before_anything_sees_them():
    body, what = sources.filter_dace((FIX / "dace_wasp18_cone.json").read_bytes())
    text = body.decode()
    assert not any(x in text for x in FAKE_PI) and "PI fields dropped" in what
    public, hidden = sources.read_filtered_dace(body)
    assert len(public) == 2 and hidden == 1 and all(v["status_published"] is True for v in public)
    assert sources.parse_dace_visits(b"") == []


def test_no_pi_data_reaches_the_pack_or_the_cache(tmp_path):
    cache = tmp_path / "cache"
    pack.build_pack("Synthetic star", tmp_path / "pack", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                    fetcher=FixtureFetcher(cache_dir=cache), ra=24.354305, dec=-45.67788, coord_source="simbad")
    # a second build reads the cache
    q = pack.build_pack("Synthetic star", tmp_path / "pack2", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=FixtureFetcher(cache_dir=cache), ra=24.354305, dec=-45.67788, coord_source="simbad")
    assert q["status"]["archive"]["n_public"] == 2 and q["status"]["archive"]["n_not_public"] == 1
    files = [f for d in (tmp_path / "pack", tmp_path / "pack2", cache) for f in d.rglob("*") if f.is_file()]
    assert any(f.parent == cache for f in files) and any("archive-" in f.name for f in files)
    for f in files:
        text = f.read_bytes().decode("utf-8", errors="replace")
        assert not any(x in text for x in FAKE_PI), f


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


def test_a_404_is_no_match_only_for_dace(tmp_path, monkeypatch):
    p = build(tmp_path)  # the DACE name and cone searches answer 404
    arch = p["status"]["archive"]
    assert arch["checked"] and not arch["already_observed"] and "does not distinguish" in arch["no_match_note"]
    assert "does not distinguish" in (tmp_path / "pack" / "README.md").read_text()

    def not_found_elsewhere(self, full, data):
        if "sim-tap" in full or "RTL_" in full:
            raise sources.NotFound(f"{full}: HTTP 404")
        return sources.Fetched(full, fixture_answer(full, data), "2026-10-21T12:00:00+00:00")

    monkeypatch.setattr(sources.Fetcher, "_request", not_found_elsewhere)
    q = pack.build_pack("TOI-1987", tmp_path / "p2", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=sources.Fetcher(cache_dir=None))
    assert not q["status"]["rtl"]["checked"]  # an RTL 404 is "not checked", never "not reserved"
    assert q["target"]["coord_source"].startswith("MAST")  # SIMBAD's 404 falls back to MAST
    assert any(e.startswith("SIMBAD") for e in q["network_errors"]) and any(e.startswith("RTL") for e in q["network_errors"])


def test_retry_after_is_honoured(monkeypatch):
    import email.message
    import urllib.error
    import urllib.request

    assert sources.retry_after("7") == 7 and sources.retry_after(None) == 5 and sources.retry_after("9999") == 120
    assert 0 <= sources.retry_after("Wed, 21 Oct 2026 07:28:00 GMT") <= 120
    calls, slept = [], []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"ok"

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if len(calls) == 1:
            headers = email.message.Message()
            headers["Retry-After"] = "3"
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", headers, None)
        return Resp()

    monkeypatch.undo()  # the real _request, with a fake network
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sources.time, "sleep", lambda s: slept.append(s))
    got = sources.Fetcher()._request("https://example.invalid/x", None)
    assert got.body == b"ok" and len(calls) == 2 and 3 in slept


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
    reserved = main(["propose", "cheops", "HD 197481", "--today", "2026-10-21", "--out", str(tmp_path / "r"), "--no-cache"])
    assert reserved == 1 and "Reserved Target List" in capsys.readouterr().out
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


# ---------------------------------------------------------------- second review: masking, Unicode, PDFs, cache

R15 = LINT / "review15"


@pytest.mark.parametrize("text", [
    "Author page: https://arxiv.org/a/doe_j_1 lists the papers.",
    "My homepage https://cheops.unige.ch/~jdoe/ has the code.",
    "See https://dace.unige.ch/profile/jdoe for the details.",
    "Personal site unige.ch/~doe has it.",
    "This is built for our tools.",
])
def test_masking_never_hides_personal_pages(text):
    assert [f for f in draft.lint_text(text) if f["level"] == "warn"], text


@pytest.mark.parametrize("text", [
    "Checked with https://cheops.unige.ch/pht2/search-reserved-targets/ today.",
    "The ETC (https://cheops.unige.ch/pht2/exposure-time-calculator/) gives 60 ppm.",
    "The archive browser https://cheops.unige.ch/archive_browser/ lists no visit.",
    "See https://arxiv.org/abs/2406.01716 and https://doi.org/10.1051/0004-6361/202348576.",
])
def test_official_tool_pages_and_papers_are_not_flagged(text):
    assert [f for f in draft.lint_text(text) if f["level"] == "warn"] == [], draft.lint_text(text)


@pytest.mark.parametrize("text", [
    "Our previous wоrk showed this.",          # Cyrillic o
    "Оur previous work showed this.",           # Cyrillic O
    "Our previous w​ork showed this.",          # zero-width space
    "Ｏｕｒ previous work showed this.",  # fullwidth "Our"
    "Dr Jаne Dоe leads this.",              # Cyrillic a and o
    "Contact jane.doe＠unige.ch today.",          # fullwidth at
])
def test_look_alike_and_invisible_characters_are_caught(text):
    found = draft.lint_text(text)
    assert [f for f in found if f["level"] == "warn"], text
    assert any(f["rule"] == "normalised" for f in found)


def test_findings_keep_the_original_line_numbers():
    text = "Neutral line.\n​​Still neutral.\nOur previous wоrk.\n"
    found = [f for f in draft.lint_text(text) if f["level"] == "warn"]
    assert found and {f["line"] for f in found} == {3} and "wоrk" in found[0]["match"]


def test_every_line_of_the_second_review_cases_is_caught():
    for name in ("new.txt", "new2.txt"):
        text = (R15 / name).read_text()
        lines = [i for i, line in enumerate(text.splitlines(), 1) if line.strip()]
        for names in (["Jane Doe"], []):
            caught = _warn_lines(draft.lint_text(text, author_names=names))
            assert set(lines) <= caught, (name, names, [text.splitlines()[i - 1] for i in set(lines) - caught])


@pytest.mark.parametrize("text", [
    "Building on the authors' prior work, we refine the ephemeris.",
    "This extends the proposers' earlier CHEOPS programme.",
    "The light curve was obtained by this team.",
    "As shown in Paper I of this series, the planet is inflated.",
    "Using the code we developed (ref. 12) we fit the data.",
    "We thank the Swiss National Science Foundation for support.",
    "Data from the IAA-CSIC and the OCA are used.",
])
def test_third_person_self_reference_funding_and_hyphenated_institutions(text):
    assert [f for f in draft.lint_text(text) if f["level"] == "warn"], text


def test_pdf_metadata_images_and_hidden_captions():
    pytest.importorskip("pypdf")
    meta = draft.lint_files([R15 / "meta.pdf"], author_names=["Jane Doe"])
    assert any(f["file"] == "meta.pdf (metadata)" and f["rule"].startswith("author-name") for f in meta)
    image = draft.lint_files([R15 / "image.pdf"])
    assert any(f["rule"] == "images" and f["match"] == "1 image not scanned (text in images cannot be checked)"
               for f in image)
    caption = draft.lint_files([R15 / "caption.pdf"])
    assert {"self-reference", "institution"} <= {f["rule"] for f in caption if f["level"] == "warn"}
    with pytest.raises(draft.LintInputError, match="image not scanned"):
        draft.lint_files([R15 / "outlined.pdf"])


def test_lint_cli_prints_the_images_note(capsys):
    pytest.importorskip("pypdf")
    from setuhq.cli import main

    main(["propose", "lint", str(R15 / "image.pdf")])
    assert "1 image not scanned (text in images cannot be checked)" in capsys.readouterr().out


def _raw_cache_entry(fetcher, ra=24.354305, dec=-45.67788):
    """A cache entry as 32dd20e wrote it: the raw DACE answer, metadata without the 'filtered' marker."""
    params = {"limit": "2000", "filters": json.dumps({"pos": {"ra": ra, "dec": dec, "radius": 30.0 / 3600.0}}),
              "sort": "{}"}
    import urllib.parse

    full = sources.DACE_CHEOPS + "?" + urllib.parse.urlencode(params)
    path = fetcher._cache_path(full, ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (FIX / "dace_wasp18_cone.json").read_bytes()
    path.write_bytes(raw)
    path.with_suffix(".json.json").write_text(json.dumps({"url": full, "fetched_at": "2026-10-21T10:00:00+00:00",
                                                           "sha256": "x"}))
    return path


def test_the_startup_sweep_deletes_raw_entries(tmp_path):
    cache = tmp_path / "cache"
    old = _raw_cache_entry(sources.Fetcher(cache_dir=cache))
    swept = sources.Fetcher(cache_dir=cache).swept
    assert old.name in swept and not old.exists() and not old.with_suffix(".json.json").exists()


def test_an_old_raw_cache_entry_is_swept_on_startup(tmp_path):
    cache = tmp_path / "cache"
    old = _raw_cache_entry(sources.Fetcher(cache_dir=cache))
    orphan = cache / "2026-10-20-0123456789abcdef.json"
    orphan.write_bytes((FIX / "dace_wasp18_cone.json").read_bytes())  # raw data with no metadata at all
    p = pack.build_pack("Synthetic star", tmp_path / "pack", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=FixtureFetcher(cache_dir=cache), ra=24.354305, dec=-45.67788, coord_source="simbad")
    assert not orphan.exists()
    # the raw entry was deleted; the path now holds the filtered copy fetched again
    assert json.loads(old.with_suffix(".json.json").read_text()).get("filtered")
    arch = p["status"]["archive"]
    assert arch["n_public"] == 2 and arch["n_not_public"] == 1
    for f in [*cache.rglob("*"), *(tmp_path / "pack").rglob("*")]:
        if f.is_file():
            assert not any(x in f.read_text(errors="replace") for x in FAKE_PI), f


def test_an_unfiltered_cache_hit_is_never_read(tmp_path):
    cache = tmp_path / "cache"
    fetcher = FixtureFetcher(cache_dir=cache)  # the startup sweep has run on an empty cache
    old = _raw_cache_entry(fetcher)
    got = sources.dace_cone(fetcher, 24.354305, -45.67788, 30.0 / 3600.0)
    assert len(got["public_visits"]) == 2 and got["n_not_public"] == 1 and got["fetched"].filtered
    assert old.exists() and not any(x in old.read_text() for x in FAKE_PI)  # replaced by the filtered copy


def test_dace_name_search_keeps_only_the_named_object():
    assert sources.same_object("WASP-18", "WASP-18") and sources.same_object("WASP-18", "WASP-18 b")
    assert sources.same_object("TOI-1987", "TOI-1987.01")
    assert not sources.same_object("WASP-18", "WASP-187 b") and not sources.same_object("WASP-18", "WASP-180")


def test_dace_is_also_queried_by_the_users_name_and_toi_tic_aliases(tmp_path):
    f = FixtureFetcher(cache_dir=None)
    p = pack.build_pack("WASP-18", tmp_path / "pack", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC), fetcher=f)
    # SIMBAD does not know "WASP-18" in the fixtures, so only the user's own name finds the visits
    assert p["status"]["archive"]["n_public"] == 2
    queries = [s.get("query") for s in p["sources"] if s.get("query")]
    assert any(q == "name WASP-18" for q in queries)
    q = pack.build_pack("TOI-1987", tmp_path / "p2", root=ROOT, now=datetime(2026, 10, 21, 12, tzinfo=UTC),
                        fetcher=FixtureFetcher(cache_dir=None))
    assert q["status"]["archive"]["checked"] and set(q["status"]["archive"]["no_match_queries"]) >= {"name", "name2"}

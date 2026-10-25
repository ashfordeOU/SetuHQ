# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The feed embargo: a signal that matches no known TOI never reaches the public catalogue, site or logs."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import setuhq.discover as dv
from setuhq.discover import Target, Toi, embargo_catalog, embargo_setting, held_line, public_catalog

ROOT = Path(__file__).resolve().parents[1]
RUN_TIME = datetime(2026, 10, 24, 6, 17, tzinfo=timezone.utc)

# The withheld signal: none of these may appear in anything public.
NEW_TIC, NEW_T, NEW_P, NEW_DEPTH, NEW_ID = 987654321, 2345.6789, 7.654321, 4987.613, "tess-embargo-secret"
SECRETS = [str(NEW_TIC), "2345.67", "2345.68", "7.654", "4987.6", NEW_ID]
# The known-TOI match: it still publishes.
KNOWN_TIC, KNOWN_T, KNOWN_P = 123450001, 2000.0, 3.3333
KNOWN_TOI = Toi(name="9999.01", period=KNOWN_P, tranmid=2459000.0, period_err=1e-5, tranmid_err=1e-3, duration_hours=2.0)
TARGETS = {NEW_TIC: Target(NEW_TIC),
           KNOWN_TIC: Target(KNOWN_TIC, toi_periods=[KNOWN_P], toi_names=[KNOWN_TOI.name], tois=[KNOWN_TOI])}


def _cand(t, p, depth, cid, sector):
    return SimpleNamespace(passed=True, flags=(), depth_ppm=depth, period_days=p, n_transits=3, fap=1 / 2001,
                           sector=sector, t_center=t, time_unit="BTJD", t_start=t - 0.05, t_end=t + 0.05,
                           snr=11.0, score=1.0, n_reviewers=3, candidate_id=cid)


class _Boom:
    """A candidate whose feed check raises: an error on the target after its other candidates were handled."""
    @property
    def passed(self):
        raise RuntimeError("boom")


@pytest.fixture
def fake_search(monkeypatch):
    """run_discovery over the two targets above, with the archive, MAST and the pipeline replaced by stand-ins.
    The feed rule itself (feed_entry), the TOI match and the catalogue writing are the real code. The returned
    state switches the withheld signal off (``with_new``) or ends the new target with an error (``error``)."""
    state = {"with_new": True, "error": False}

    def pipeline(config, curves, reviewers, out, **kw):
        tic = curves[0].tic
        t, p, d, cid = (NEW_T, NEW_P, NEW_DEPTH, NEW_ID) if tic == NEW_TIC else (KNOWN_T, KNOWN_P, 900.0, "tess-known-1")
        # The same signal in both reviewed sectors (the feed rule's two-sector part).
        found = [_cand(t, p, d, cid, 1), _cand(t, p, d, cid + "b", 2)]
        if tic == NEW_TIC:
            found = (found if state["with_new"] else []) + ([_Boom()] if state["error"] else [])
        return SimpleNamespace(candidates=found)

    monkeypatch.setattr(dv, "fetch_toi_targets", lambda: dict(TARGETS))
    monkeypatch.setattr(dv, "load_tess", lambda label: [SimpleNamespace(tic=int(label.split()[1]), provenance={"sector": s})
                                                         for s in (1, 2)])
    monkeypatch.setattr(dv, "run_pipeline", pipeline)
    return state


def _config(tmp_path, extra=""):
    path = tmp_path / "discovery.toml"
    path.write_text('[run]\nname = "discovery"\n' + extra)
    return path


def _discover(tmp_path, *, extra="", run_time=RUN_TIME, catalog=None, **kw):
    catalog = catalog or tmp_path / "docs" / "catalog.json"
    log = dv.run_discovery(_config(tmp_path, extra), catalog, tics=[NEW_TIC, KNOWN_TIC], run_time=run_time,
                           work_dir=tmp_path / "work", cache_root=tmp_path / "cache", **kw)
    return log, catalog


def _no_trace(text: str, where: str):
    for s in SECRETS:
        # Not preceded by a digit or a point, so 177.6549 elsewhere on the site is not the period 7.654.
        m = re.search(r"(?<![\d.])" + re.escape(s), text)
        i = m.start() if m else -1
        if i >= 0:  # report the context only: a diff of a whole built site would take minutes
            pytest.fail(f"{s!r} (the withheld signal) found in {where}: ...{text[max(0, i - 120):i + 80]}...")


def test_a_new_signal_is_withheld_without_a_count_or_a_date(fake_search, tmp_path):
    log, path = _discover(tmp_path)
    text = path.read_text()
    _no_trace(text, "the catalogue JSON")
    _no_trace(json.dumps(log), "the run log")
    cat = json.loads(text)
    assert cat["embargo"] is True
    assert [e["status"] for e in cat["candidates"]] == ["known_toi"]
    assert cat["candidates"][0]["tic"] == KNOWN_TIC and cat["candidates"][0]["toi_match"] == "9999.01"
    assert not [k for k in cat if k.startswith("held")] and "held" not in text
    assert "new" not in log and all("new" not in r and "targets" not in r for r in cat["runs"])


# The rule: a run that held a signal leaves exactly the public outputs a run without it leaves. Nothing is exempt:
# the two runs share their run time, so even the timestamps (the only fields that could legitimately differ
# between two real runs) are equal, and every byte must match.
@pytest.mark.parametrize("error", [False, True], ids=["clean", "target-error"])
def test_a_held_signal_leaves_the_public_outputs_byte_identical(fake_search, tmp_path, app_run, monkeypatch, capsys, error):
    from setuhq.cli import main

    outs = {}
    for with_new in (True, False):
        fake_search.update(with_new=with_new, error=error)
        root = tmp_path / ("with" if with_new else "without")
        (root / "docs" / "results").mkdir(parents=True)
        monkeypatch.chdir(root)  # relative paths, so each page names the same files
        monkeypatch.setattr(dv, "datetime", _FixedNow)
        (root / "cfg.toml").write_text('[run]\nname = "discovery"\n')
        main(["discover", "cfg.toml", "--catalog", "docs/catalog.json", "--site", "feed", "--work-dir", "work",
              "--cache", "cache"])
        printed = capsys.readouterr()
        site = _build_public_pages(Path("docs/catalog.json"), Path("site"), app_run)
        files = {f.relative_to(root).as_posix(): f.read_bytes() for d in ("docs", "site", "feed")
                 for f in sorted((root / d).rglob("*")) if f.is_file()}
        outs[with_new] = (printed.out, printed.err, files, site)
    held, plain = outs[True], outs[False]
    assert held[0] == plain[0] and held[1] == plain[1], "the command's output differs"
    assert held[2].keys() == plain[2].keys()
    differ = [n for n in held[2] if held[2][n] != plain[2][n]]
    assert not differ, f"public files differ when a signal is held: {differ[:10]}"
    cat = json.loads(held[2]["docs/catalog.json"])
    if error:  # the error is recorded as any other, naming its target, with or without a held signal
        assert cat["runs"][-1]["errors"] == [f"TIC {NEW_TIC}: RuntimeError: boom"]
    else:
        _no_trace(held[3], "the site of the run that held a signal")


class _FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return RUN_TIME


def test_the_embargo_is_on_by_default_and_off_only_when_asked(fake_search, tmp_path):
    from setuhq.cli import build_parser
    from setuhq.config import load_config

    assert embargo_setting(load_config(_config(tmp_path))) is True
    assert embargo_setting(load_config(_config(tmp_path, "[discover]\nembargo = true\n"))) is True
    assert embargo_setting(load_config(_config(tmp_path, '[discover]\nembargo = "no"\n'))) is True  # only false opts out
    assert embargo_setting(load_config(_config(tmp_path, "[discover]\nembargo = false\n"))) is False
    assert embargo_setting(load_config(_config(tmp_path)), publish_new=True) is False
    assert build_parser().parse_args(["discover", "c.toml"]).publish_new is False
    assert build_parser().parse_args(["discover", "c.toml", "--publish-new"]).publish_new is True
    assert dv.run_discovery.__kwdefaults__["publish_new"] is False


@pytest.mark.parametrize("how", ["flag", "config"])
def test_a_private_deployment_keeps_everything(fake_search, tmp_path, how):
    kw = {"publish_new": True} if how == "flag" else {"extra": "[discover]\nembargo = false\n"}
    log, path = _discover(tmp_path, **kw)
    cat = json.loads(path.read_text())
    assert cat["embargo"] is False and log["new"] == 1
    assert {e["status"] for e in cat["candidates"]} == {"known_toi", "new_candidate"}
    assert public_catalog(cat) is cat  # a private catalogue renders in full on the private deployment's own pages


def _build_public_pages(path, out, run_dir):
    """Every public page that reads the search catalogue: the site (app), the feed page and the dashboard."""
    import setuhq.docket as dm
    from setuhq.app import build_app
    from setuhq.dashboard import build_dashboard
    from setuhq.report import build_discovery_site

    keep = dm.query_archive
    dm.query_archive = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test"))
    try:
        build_app(run_dir, out / "app", title="t", catalog_path=path)
    finally:
        dm.query_archive = keep
    build_discovery_site(path, out / "discoveries")
    build_dashboard(run_dir, out / "dashboard", title="t", catalog_path=path)
    files = [f for f in out.rglob("*") if f.is_file() and f.suffix in (".html", ".json", ".js", ".xml", ".txt", ".svg")]
    assert files
    return "\n".join(f.read_text(errors="ignore") for f in files)


def test_public_pages_from_an_embargoed_catalogue_hold_no_trace(fake_search, tmp_path, app_run):
    _, path = _discover(tmp_path)
    out = tmp_path / "site"
    whole = _build_public_pages(path, out, app_run)
    _no_trace(whole, "the built site")
    assert str(KNOWN_TIC) in whole  # the known-TOI match still publishes
    line = held_line()
    assert line == ("Signals that match no known TOI are held for private review; "
                    "they are published only after review and reporting.")
    assert not re.search(r"\d", line)  # no number
    for f in (out / "discoveries" / "index.html", out / "dashboard" / "index.html"):
        assert line in f.read_text() or json.dumps(line)[1:-1] in f.read_text(), f
    assert line in whole


def test_the_trace_check_would_catch_a_published_signal(fake_search, tmp_path, app_run):
    """Control: the same pages built from a private catalogue (embargo off) do show the signal, so the grep above
    looks for what a leak would print."""
    _, path = _discover(tmp_path, publish_new=True)
    whole = _build_public_pages(path, tmp_path / "site", app_run)
    with pytest.raises(pytest.fail.Exception):
        _no_trace(whole, "the private site")
    for s in (str(NEW_TIC), "7.654", NEW_ID):
        assert s in whole, s


def test_pages_withhold_a_new_signal_even_from_a_catalogue_that_still_holds_one(tmp_path):
    """Defence in depth: a catalogue written before the embargo (no "embargo" key) is filtered when read."""
    from setuhq.report import build_discovery_site

    new = {"tic": NEW_TIC, "t_center": NEW_T, "time_unit": "BTJD", "duration_hours": 2.4, "depth_ppm": NEW_DEPTH,
           "snr": 11.0, "score": 1.0, "period_days": NEW_P, "found": "2026-10-24T06:17:00+00:00",
           "candidate_id": NEW_ID, "status": "new_candidate"}
    known = dict(new, tic=KNOWN_TIC, t_center=KNOWN_T, period_days=KNOWN_P, depth_ppm=900.0, candidate_id="k",
                 status="known_toi")
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"candidates": [new, known], "runs": []}))
    pub = public_catalog(json.loads(path.read_text()))
    assert [e["tic"] for e in pub["candidates"]] == [KNOWN_TIC] and not [k for k in pub if k.startswith("held")]
    _no_trace(build_discovery_site(path, tmp_path / "feed").read_text(), "the feed page")


def test_embargo_catalog_keeps_only_known_toi_entries_and_stores_nothing_about_the_rest():
    cat = {"candidates": [{"tic": NEW_TIC, "status": "new_candidate"}, {"tic": KNOWN_TIC, "status": "known_toi"},
                          {"tic": 5, "status": "something_else"}],
           "held_for_review": 3, "held_last_date": "2026-10-24", "held_on_last_date": 1,  # an earlier build's fields
           "runs": [{"time": "t", "targets": [NEW_TIC, KNOWN_TIC], "errors": []}]}
    assert embargo_catalog(cat, RUN_TIME) == 2
    assert cat == {"candidates": [{"tic": KNOWN_TIC, "status": "known_toi"}], "embargo": True,
                   "runs": [{"time": "t", "n_targets": 2, "errors": []}]}


def test_the_discover_command_prints_no_detail_of_a_held_signal(fake_search, tmp_path, monkeypatch, capsys):
    from setuhq.cli import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs" / "results").mkdir(parents=True)
    main(["discover", str(_config(tmp_path)), "--catalog", str(tmp_path / "cat.json"), "--site", str(tmp_path / "s"),
          "--work-dir", str(tmp_path / "w"), "--cache", str(tmp_path / "c")])
    out = capsys.readouterr()
    _no_trace(out.out + out.err, "the command's output (public in the Actions log)")
    assert "held" not in out.out and "new candidates" not in out.out
    assert out.out.startswith("targets reviewed this run: 2, known TOI matches: 1\n")


def _public_workflows(comments: bool = True):
    """Each workflow's text; without ``comments``, only what runs (a comment may name the flag to forbid it)."""
    strip = (lambda t: t) if comments else (lambda t: "\n".join(re.sub(r"(^|\s)#.*$", "", ln) for ln in t.splitlines()))
    return {p.name: strip(p.read_text()) for p in (ROOT / ".github" / "workflows").glob("*.yml")}


def test_no_public_workflow_turns_the_embargo_off():
    flows = _public_workflows(comments=False)
    assert "discover.yml" in flows
    for name, text in flows.items():
        assert "--publish-new" not in text and "publish_new" not in text, name
        assert not re.search(r"embargo\s*=\s*false", text, re.I), name
    # The config the scheduled batch runs does not opt out either.
    cmd = re.search(r"setuhq discover (\S+)", flows["discover.yml"]).group(1)
    from setuhq.config import load_config
    assert embargo_setting(load_config(ROOT / cmd)) is True
    for cfg in (ROOT / "configs").rglob("*.toml"):
        assert not re.search(r"embargo\s*=\s*false", cfg.read_text(), re.I), cfg


def test_the_workflow_checks_the_embargo_before_it_commits():
    text = _public_workflows()["discover.yml"]
    assert text.index("Embargo check") < text.index("git commit")
    assert "upload-artifact@" not in text  # only the Pages artifact (the embargoed site) is uploaded

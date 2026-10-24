# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Protocol v4's capabilities as tools: the MCP tools (find_eclipsing_binary, rotation_period, find_transients), the
CLI commands (setuhq binaries, rotation, transients), the validation record and its status wording. Offline."""

import json
import re
from pathlib import Path

import numpy as np
import pytest

from setuhq import binaries as B
from setuhq import rotation as R
from setuhq import stellar_tools as st
from setuhq import transients as X
from setuhq.cli import main

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "docs/results/stellar_validation_v4.json").read_text())
PROTOCOL = json.loads((ROOT / "docs/results/stellar_validation_protocol_v4.json").read_text())
STATUS_WORDS = ("validated", "partly validated", "not validated")


def _check(env, tool):
    assert env["tool"] == tool and set(env) == {"tool", "result", "provenance", "honesty"}
    json.dumps(env, allow_nan=False)
    low = json.dumps(env).lower()
    for word in ("superintelligence", "confirmed binary", "confirmed transient", "new transient", "new binary", "discovered"):
        assert word not in low.replace("never a new, discovered or confirmed object", "").replace(
            "never a confirmed or new binary", ""), word
    return env["result"]


def _t(days=27.0, cad=10.0):
    t = np.arange(1325.0, 1325.0 + days, cad / 1440)
    return t[(t < 1338) | (t > 1339)]


@pytest.fixture
def eb_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    t = _t()
    f = B.synthetic_eb(t, 2.7, 1325.3, 0.2, 0.08, 0.5, 0.04) + np.random.default_rng(1).normal(0, 1e-3, t.size)
    p = tmp_path / "eb.csv"
    np.savetxt(p, np.c_[t, f, np.full(t.size, 1e-3)], delimiter=",", header="time,flux,flux_err", comments="")
    return p


@pytest.fixture
def rot_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    t = _t(cad=2.0)
    rng = np.random.default_rng(2)
    f = R.spot_model(t, 3.0, 5e-3, rng, n_spots=1) + rng.normal(0, 1e-3, t.size)
    p = tmp_path / "rot.csv"
    np.savetxt(p, np.c_[t, f], delimiter=",", header="time,flux", comments="")
    return p


@pytest.fixture
def tr_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    t = _t(cad=2.0)
    f = 1 + np.random.default_rng(3).normal(0, 1e-3, t.size) + X.flare_model(t, 1330.3, 0.02)
    p = tmp_path / "tr.csv"
    np.savetxt(p, np.c_[t, f], delimiter=",", header="time,flux", comments="")
    return p


def test_find_eclipsing_binary_tool_with_advisory_vetting_hints(eb_csv):
    r = _check(st.find_eclipsing_binary(csv_path="eb.csv", transit_period=2.7, transit_epoch=1325.3,
                                        transit_duration_days=0.12), "find_eclipsing_binary")
    assert r["eb_candidate"] and r["period"] == pytest.approx(2.7, rel=0.005)
    assert "not used by SetuHQ's planet vetting" in r["vetting_hints"]["note"]
    assert r["validation_status"] == st.NO_RECORD  # the data root here has no record: never presented as validated
    from setuhq.tools import ToolError

    with pytest.raises(ToolError, match="together"):
        st.find_eclipsing_binary(csv_path="eb.csv", transit_period=2.7)


def test_rotation_period_tool(rot_csv):
    env = st.rotation_period(csv_path="rot.csv")
    r = _check(env, "rotation_period")
    assert r["detected"] and r["period"] == pytest.approx(3.0, rel=0.1)
    assert any("13 days" in h for h in env["honesty"])


def test_find_transients_tool(tr_csv):
    env = st.find_transients(csv_path="tr.csv", momentum_dump_times=[1342.0])
    r = _check(env, "find_transients")
    assert [c["class_hint"] for c in r["candidates"]] == ["flare-like"]
    assert any("never a new, discovered or confirmed object" in h for h in env["honesty"])


def test_the_tools_are_registered_after_the_stellar_ones():
    from setuhq.tools import TOOLS

    names = [fn.__name__ for fn, _ in TOOLS]
    assert names[-6:] == ["find_flares", "pulsation_spectrum", "get_cheops_lightcurve", "find_eclipsing_binary",
                          "rotation_period", "find_transients"]


def test_cli_binaries_rotation_transients_on_csv(eb_csv, rot_csv, tr_csv, tmp_path, capsys):
    for cmd, csv, kind in (("binaries", eb_csv, "setuhq-binaries/1"), ("rotation", rot_csv, "setuhq-rotation/1"),
                           ("transients", tr_csv, "setuhq-transients/1")):
        out = tmp_path / f"{cmd}.json"
        assert main([cmd, str(csv), "--out", str(out)]) == 0
        rec = json.loads(out.read_text())
        assert rec["kind"] == kind and rec["provenance"]["inputs"][0]["sha256"]
        assert rec["validation_status"].split(" (")[0] in STATUS_WORDS
    printed = capsys.readouterr().out
    assert "eclipsing-binary candidate" in printed and "rotation period 3." in printed and "transient candidates" in printed
    assert "about 13 d" in printed
    # every command prints its capability's status, naming the v4 record
    for what in ("eclipsing-binary analysis: ", "rotation measurement: ", "transient detection: "):
        assert what in printed
    assert printed.count("docs/results/stellar_validation_v4.md") == 3


def test_the_cli_prints_the_status_the_record_states(monkeypatch, capsys):
    monkeypatch.setenv("SETUHQ_ROOT", str(ROOT))
    from setuhq.stellar_cli import _status

    for cap, what in (("binaries", "eclipsing-binary analysis"), ("rotation", "rotation measurement"),
                      ("transients", "transient detection")):
        assert _status(cap, what) == RECORD["capabilities"][cap]["label"]
    out = capsys.readouterr().out
    for cap in ("binaries", "rotation", "transients"):
        assert RECORD["capabilities"][cap]["label"] + " against published results" in out


def test_record_points_at_the_protocol_committed_before_it():
    import hashlib

    assert RECORD["protocol_sha256"] == hashlib.sha256((ROOT / RECORD["protocol_file"]).read_bytes()).hexdigest()
    assert len(RECORD["protocol_commit"] or "") == 40 and RECORD["protocol_version"] == 4
    assert RECORD["seed"] == PROTOCOL["seed"] and len(RECORD["code_fingerprint"]) == 64
    assert [c["check"] for c in RECORD["checks"]] == [c["id"] for c in PROTOCOL["checks"]]


def test_status_wording_follows_the_rule_with_its_count():
    for cap in ("binaries", "rotation", "transients"):
        c = RECORD["capabilities"][cap]
        checks = [x for x in RECORD["checks"] if x["capability"] == cap]
        k = sum(x["result"] == "pass" for x in checks)
        assert (c["passed"], c["of"]) == (k, len(checks))
        word = "validated" if k == len(checks) else ("partly validated" if k > len(checks) / 2 else "not validated")
        assert c["status"] == word and c["label"] == f"{word} ({k} of {len(checks)} checks pass)"


def test_counted_checks_use_held_out_targets_and_the_splits_are_fixed():
    for cap, n_tune in (("binaries", 6), ("rotation", 6), ("transients", 5)):
        tg = PROTOCOL[cap]["targets"]
        assert [x["split"] for x in tg[:n_tune]] == ["tuning"] * n_tune
        assert all(x["split"] == "held_out" for x in tg[n_tune:])
    res = RECORD["results"]
    assert res["eb_catalogue"]["held_out"]["n"] == 24 and res["eb_catalogue"]["tuning"]["n"] == 6
    assert res["rot_catalogue"]["held_out"]["n"] == 24 and res["tr_supernovae"]["held_out"]["n"] == 15


def test_v4_documents_never_call_a_candidate_new_or_confirmed():
    for rel in ("docs/results/stellar_validation_v4.md", "docs/STELLAR.md"):
        low = (ROOT / rel).read_text().lower()
        assert "superintelligence" not in low
        for bad in ("new eclipsing binary", "new transient", "new supernova", "confirmed eclipsing", "confirmed transient",
                    "we discovered", "setuhq discovered"):
            assert bad not in low, (rel, bad)
    assert re.search(r"candidate, never new and never confirmed", (ROOT / "docs/results/stellar_validation_v4.md").read_text())

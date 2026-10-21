# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The stellar MCP tools and CLI commands (find_flares, pulsation_spectrum, get_cheops_lightcurve; setuhq flares,
pulsations, cheops), offline: envelopes, labels, provenance and the CHEOPS acknowledgement on every CHEOPS output."""

import gzip
import json
import math
from pathlib import Path

import numpy as np
import pytest

from setuhq import flares as fl
from setuhq import stellar_tools as st
from setuhq.cli import main

from test_cheops import FIXTURE, assert_credited

ROOT = Path(__file__).resolve().parents[1]


def _check(env, tool):
    assert env["tool"] == tool and set(env) == {"tool", "result", "provenance", "honesty"}
    json.dumps(env, allow_nan=False)
    low = json.dumps(env).lower()
    assert "superintelligence" not in low and "confirmed flare" not in low and "discovered" not in low
    return env["result"]


@pytest.fixture
def flare_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    rng = np.random.default_rng(3)
    t = np.arange(1400.0, 1406.0, 2 / 1440)
    f = 1 + rng.normal(0, 5e-4, t.size)
    for tp, fw, a in ((1401.0, 6.0, 0.02), (1404.2, 10.0, 0.01)):
        f *= 1 + fl.integrated_template(t, tp, fw / 1440, a, exposure=2 / 1440)
    p = tmp_path / "star.csv"
    np.savetxt(p, np.c_[t, f, np.full(t.size, 5e-4)], delimiter=",", header="time,flux,flux_err", comments="")
    return p


@pytest.fixture
def puls_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    rng = np.random.default_rng(4)
    t = np.arange(0.0, 15.0, 2 / 1440)
    y = 1 + rng.normal(0, 3e-4, t.size) + 2e-3 * np.sin(2 * math.pi * 14.2 * t) + 1e-3 * np.sin(2 * math.pi * 17.9 * t + 1)
    p = tmp_path / "puls.csv"
    np.savetxt(p, np.c_[t, y], delimiter=",", header="time,flux", comments="")
    return p


def test_find_flares_tool(flare_csv):
    env = st.find_flares(csv_path="star.csv", teff=3200, radius_rsun=0.3)
    r = _check(env, "find_flares")
    assert r["summary"]["n_flares"] == 2 and r["inverted_null"]["false_positives"] == 0
    assert all(f["e_bol_erg"] > 0 for f in r["flares"])
    assert r["validation_status"] == "unvalidated"   # no validation record under this data root
    assert any("detected at the significance" in h for h in env["honesty"])
    assert any("9000 K" in h for h in env["honesty"])
    assert env["provenance"]["sources"][0]["sha256"]
    r2 = _check(st.find_flares(csv_path="star.csv"), "find_flares")
    assert all(f["e_bol_erg"] is None and f["status"] == "unavailable" for f in r2["flares"])


def test_find_flares_tool_cheops_mission_carries_the_acknowledgement(flare_csv):
    env = st.find_flares(csv_path="star.csv", mission="CHEOPS")
    assert_credited({"honesty": env["honesty"], "c": __import__("setuhq.cheops", fromlist=["x"]).credit([])})
    assert any("not affiliated" in h for h in env["honesty"]) and any("ESA mission" in h for h in env["honesty"])


def test_pulsation_spectrum_tool(puls_csv):
    env = st.pulsation_spectrum(csv_path="puls.csv", teff=7500, max_frequencies=10)
    r = _check(env, "pulsation_spectrum")
    fs = sorted(x["frequency"] for x in r["prewhitening"]["frequencies"] if x["significant"])
    assert any(abs(f - 14.2) < 0.01 for f in fs) and any(abs(f - 17.9) < 0.01 for f in fs)
    assert r["type"]["label"] in ("δ Scuti", "hybrid δ Scuti/γ Doradus", "unclear") and r["type"]["confidence"] != "high"
    from setuhq.tools import ToolError

    with pytest.raises(ToolError):
        st.pulsation_spectrum(csv_path="puls.csv", n_surrogates=99)


def _cheops_cache(root: Path):
    ex = json.loads(FIXTURE.read_text())
    meta = ex["meta"]
    vdir = root / "cache" / "cheops" / "visits"
    vdir.mkdir(parents=True)
    payload = {"meta": meta, "aperture": "default", "arrays": ex["arrays"]}
    (vdir / f"{meta['file_key']}_default.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    from setuhq import cheops as ch

    (vdir / "GJ_65.json").write_text(json.dumps({"target": "GJ 65", "visits": [meta], "n_public": 1,
                                                 "n_not_public_dropped": 0, **ch.credit([meta])}))
    return meta


def test_get_cheops_lightcurve_tool_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    meta = _cheops_cache(tmp_path)
    env = st.get_cheops_lightcurve("GJ 65", offline=True, include_points=True)
    r = _check(env, "get_cheops_lightcurve")
    assert r["visits"][0]["points"]["time_btjd"] and r["n_public_visits"] == 1
    assert_credited(env, [meta["file_key"]])
    from setuhq.tools import ToolError

    with pytest.raises(ToolError, match="offline"):
        st.get_cheops_lightcurve("Nowhere", offline=True)


def test_mcp_server_lists_the_stellar_tools():
    pytest.importorskip("mcp")
    from setuhq.mcp_server import main as mcp_main
    from setuhq.tools import TOOLS

    names = [fn.__name__ for fn, _ in TOOLS]
    assert names[-3:] == ["find_flares", "pulsation_spectrum", "get_cheops_lightcurve"]
    assert mcp_main(["--list-tools"]) == 0


def test_cli_flares_and_pulsations_on_csv(flare_csv, puls_csv, tmp_path, capsys):
    out = tmp_path / "fl.json"
    assert main(["flares", str(flare_csv), "--teff", "3200", "--radius", "0.3", "--out", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert rec["kind"] == "setuhq-flares/1" and rec["results"][0]["summary"]["n_flares"] == 2
    assert rec["provenance"]["code_fingerprint"] and rec["provenance"]["inputs"][0]["sha256"]
    assert "not a confirmation" in rec["label"] and rec["ffd"]["energy"]
    out2 = tmp_path / "pu.json"
    assert main(["pulsations", str(puls_csv), "--max-frequencies", "8", "--out", str(out2)]) == 0
    rec2 = json.loads(out2.read_text())
    assert rec2["kind"] == "setuhq-pulsations/1" and rec2["prewhitening"]["n_significant"] >= 2
    printed = capsys.readouterr().out
    assert "flares detected" in printed and "frequencies at S/N" in printed


def test_cli_cheops_offline_record_is_credited(tmp_path, monkeypatch, capsys):
    meta = _cheops_cache(tmp_path)
    out = tmp_path / "ch.json"
    assert main(["cheops", "GJ 65", "--offline", "--cache", str(tmp_path / "cache"), "--flares", "--out", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert_credited(rec, [meta["file_key"]])
    assert "flares" in rec["visits"][0]
    printed = capsys.readouterr().out
    assert "CHEOPS is an ESA mission" in printed and "not affiliated" in printed
    assert main(["cheops", "Nowhere", "--offline", "--cache", str(tmp_path / "cache")]) == 2


def test_docs_carry_the_disclaimer_and_acknowledgement():
    from setuhq.cheops import ACKNOWLEDGEMENT, DISCLAIMER

    for rel in ("docs/STELLAR.md", "docs/results/stellar_validation.md"):
        text = (ROOT / rel).read_text()
        assert DISCLAIMER in text and ACKNOWLEDGEMENT.split(". ")[0] in text, rel
        for word in ("Benz", "Hoyer", "Fortier", "CH_PR100018"):
            assert word in text, (rel, word)
        low = text.lower()
        assert "superintelligence" not in low
        assert "confirmed flare" not in low and "we discovered" not in low


def test_validation_record_has_protocol_seed_fingerprint_and_labels():
    rec = json.loads((ROOT / "docs/results/stellar_validation.json").read_text())
    assert rec["protocol"]["seed"] and len(rec["protocol_sha256"]) == 64
    for cap in ("flares", "pulsations", "cheops"):
        assert rec["capabilities"][cap]["status"] in ("validated", "partly validated", "unvalidated")
    assert all(len(v["code_fingerprint"]) == 64 for v in rec["items"].values() if v.get("code_fingerprint"))
    assert_credited(rec["cheops_credit"], [])

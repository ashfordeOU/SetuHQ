# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The MCP server and the tools it exposes, on committed data (the pi Men run, the catalogue). No network."""

import json
import sys
from pathlib import Path

import pytest

from setuhq import tools
from setuhq.tools import ToolError

ROOT = Path(__file__).resolve().parents[1]
RUN = "runs/tess-pi-men-s1"
SUBJECT = ROOT / RUN / "subjects" / "tess-fa3483ce6f83.json"  # three transits of pi Men c, stored
SECRET = "sk-test-NEVER-WRITE-THIS"
EXPECTED = ["search_catalogue", "get_planet", "get_star", "list_candidates", "get_candidate", "vet_lightcurve",
            "fit_transit", "compute_fap", "run_pipeline_csv", "run_pipeline_tess", "rv_semi_amplitude", "transit_depth",
            "microlensing_magnification", "habitable_zone", "benchmark_results", "sentinel_providers",
            "cheops_proposal_pack",
            "find_flares", "pulsation_spectrum", "get_cheops_lightcurve", "find_eclipsing_binary", "rotation_period",
            "find_transients"]


@pytest.fixture(autouse=True)
def data_root(monkeypatch):
    monkeypatch.setenv("SETUHQ_ROOT", str(ROOT))


@pytest.fixture(scope="module")
def arrays():
    d = json.loads(SUBJECT.read_text())
    return {"time": d["time"], "flux": d["flux"], "flux_err": d["flux_err"]}


def _check(env, tool):
    """Every tool answers in one shape: result, provenance (code, sources, time) and honesty labels."""
    assert env["tool"] == tool
    assert set(env) == {"tool", "result", "provenance", "honesty"}
    assert env["provenance"]["setuhq_version"] and env["provenance"]["computed_at"]
    assert env["honesty"] and all(isinstance(h, str) and h for h in env["honesty"])
    json.dumps(env, allow_nan=False)  # strict JSON: no NaN or infinity
    assert "superintelligence" not in json.dumps(env).lower()
    return env["result"]


# ---------------------------------------------------------------- the server


@pytest.fixture(scope="module")
def server():
    pytest.importorskip("mcp")
    from setuhq.mcp_server import build_server

    return build_server()


def _run(coro_fn, *args):
    import anyio

    return anyio.run(coro_fn, *args)


def test_server_lists_every_tool_with_a_description(server):
    listed = _run(server.list_tools)
    assert [t.name for t in listed] == EXPECTED == [fn.__name__ for fn, _ in tools.TOOLS]
    for t in listed:
        assert t.description and len(t.description) > 40
        schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None)
        assert schema["type"] == "object"
    writes = {t.name for t in listed if not (t.annotations.read_only_hint if hasattr(t.annotations, "read_only_hint")
                                              else t.annotations.readOnlyHint)}
    assert writes == {"run_pipeline_csv", "run_pipeline_tess", "cheops_proposal_pack", "get_cheops_lightcurve"}


def _text(result):
    return json.loads(result.content[0].text)


def test_server_calls_a_tool_and_reports_a_refusal(server):
    env = _text(_run(server.call_tool, "get_planet", {"name": "pi Men c"}))
    assert _check(env, "get_planet")["planet"]["period"] == pytest.approx(6.27, abs=0.01)
    with pytest.raises(Exception, match="no planet named"):
        _run(server.call_tool, "get_planet", {"name": "no such planet"})


def test_server_over_stdio(tmp_path):
    """The real transport: start setuhq-mcp as a subprocess, list the tools, call one."""
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "setuhq.mcp_server"],
                                   env={"SETUHQ_ROOT": str(ROOT), "PATH": "", "PYTHONPATH": str(ROOT / "src")})

    async def go():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                called = await session.call_tool("habitable_zone", {"teff": 5772, "luminosity_lsun": 1.0})
                return [t.name for t in listed.tools], json.loads(called.content[0].text)

    names, env = anyio.run(go)
    assert names == EXPECTED
    assert _check(env, "habitable_zone")["limits"]["runaway_greenhouse"]["distance_au"] == pytest.approx(0.95, abs=0.02)


def test_mcp_main_lists_tools(capsys):
    pytest.importorskip("mcp")
    from setuhq.mcp_server import main

    assert main(["--list-tools"]) == 0
    assert capsys.readouterr().out.split()[0] == "search_catalogue"


# ---------------------------------------------------------------- each tool on committed data


def test_catalogue_tools():
    found = _check(tools.search_catalogue("pi Men"), "search_catalogue")
    assert "pi Men c" in {r["name"] for r in found["rows"]}
    transit = _check(tools.search_catalogue("", method="transit", limit=5), "search_catalogue")
    assert transit["shown"] == 5 and transit["matches"] > 1000
    env = tools.get_star("pi Men")
    star = _check(env, "get_star")
    assert {"pi Men b", "pi Men c"} <= {p["name"] for p in star["planets"]}
    assert env["provenance"]["sources"][0]["sha256"] and "did not discover" in " ".join(env["honesty"])
    with pytest.raises(ToolError):
        tools.get_planet("pi Men z")


def test_run_tools_read_the_stored_pi_men_run():
    listed = _check(tools.list_candidates(RUN), "list_candidates")
    assert listed["n"] == 7 and _check(tools.list_candidates(RUN, passed_only=True), "list_candidates")["n"] == 6
    env = tools.get_candidate("tess-fa3483ce6f83-000", RUN)
    got = _check(env, "get_candidate")
    assert got["candidate"]["passed"] is True and got["candidate"]["period_days"] == pytest.approx(6.27, abs=0.01)
    assert got["run"]["config_sha256"] and got["run"]["inputs"][0]["sector"] == 1 and got["run"]["inputs"][0]["author"] == "SPOC"
    assert {r["reviewer"] for r in got["reviews"]} >= {"claude-volunteer", "volunteer-typical"}
    assert any(r["rationale"] for r in got["reviews"])
    assert got["run"]["sentinels"]["claude-volunteer"]["provider_label"].startswith("Claude")
    assert any("not a discovery" in h for h in env["honesty"]) and any("not people" in h for h in env["honesty"])
    rejected = tools.get_candidate("tess-04b815001aa6-006", RUN)
    assert any(h.startswith("This dip did not pass vetting") for h in rejected["honesty"])
    with pytest.raises(ToolError):
        tools.get_candidate("nope", RUN)


def test_vet_lightcurve_on_pi_men_c(arrays):
    # The stored dip at BTJD 1331.77: on the 6.27 d ephemeris, passes vetting.
    got = _check(tools.vet_lightcurve(**arrays, t_start=1331.72, t_end=1331.822, target="TIC 261136679"), "vet_lightcurve")
    assert got["passed"] is True and got["on_periodic_ephemeris"] is True
    assert got["periodic_signal"]["period_days"] == pytest.approx(6.27, abs=0.05)
    assert got["metrics"]["snr"] > 7
    auto = _check(tools.vet_lightcurve(**arrays), "vet_lightcurve")  # no window: the strongest signal's first transit
    assert auto["window"][0] == pytest.approx(1325.5, abs=0.2)
    with pytest.raises(ToolError):
        tools.vet_lightcurve(time=[1, 2], flux=[1, 1])


def test_fit_transit_on_pi_men_c(arrays):
    got = _check(tools.fit_transit(t0=1331.77, duration_hours=2.9, depth_ppm=250, period_days=6.27, teff=6037, logg=4.4,
                                   **arrays), "fit_transit")
    fit = got["fit"]
    assert 150 < fit["depth_ppm"] < 400 and 2.0 < fit["t14_hours"] < 4.0
    assert got["limb_darkening"]["source"].startswith("Claret")


def test_compute_fap_is_bounded(arrays):
    env = tools.compute_fap(**arrays, n_trials=10)
    got = _check(env, "compute_fap")
    assert got["trials"] == 10 and got["fap"] >= 1 / 11
    if got["upper_bound"]:
        assert got["fap_label"].startswith("< ") and any("upper bound" in h for h in env["honesty"])
    with pytest.raises(ToolError):
        tools.compute_fap(**arrays, n_trials=10_000)


def test_methods_helpers():
    k = _check(tools.rv_semi_amplitude(4332.59, 1.0, 1.0), "rv_semi_amplitude")["K_m_s"]
    assert k == pytest.approx(12.5, abs=0.2)  # Jupiter moves the Sun by about 12.5 m/s
    depth = _check(tools.transit_depth(planet_radius_rearth=1.0, star_radius_rsun=1.0, teff=5772), "transit_depth")
    assert depth["geometric_depth_ppm"] == pytest.approx(84, abs=1)
    assert depth["limb_darkened_depth_ppm"] > depth["geometric_depth_ppm"]  # a central transit covers the bright centre
    assert _check(tools.microlensing_magnification(1.0), "microlensing_magnification")["A"] == pytest.approx(3 / 5 ** 0.5)
    hz = _check(tools.habitable_zone(5780, 1.0), "habitable_zone")["limits"]
    assert hz["runaway_greenhouse"]["distance_au"] < 1.0 < hz["maximum_greenhouse"]["distance_au"]
    for bad in (lambda: tools.transit_depth(), lambda: tools.microlensing_magnification(0), lambda: tools.habitable_zone(9000, 1)):
        with pytest.raises(ToolError):
            bad()


@pytest.mark.parametrize("which", sorted(tools.BENCHMARKS))
def test_benchmark_results(which):
    env = tools.benchmark_results(which)
    got = _check(env, "benchmark_results")
    assert got["which"] == which and got["data"] and env["provenance"]["sources"][0]["sha256"]
    if which == "real_tois":
        assert got["data"]["sentinels"]["agreement"]["phi"] == pytest.approx(0.89, abs=0.01)


def test_sentinel_providers_never_show_a_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tools.sentinel_providers()
    rows = {r["type"]: r for r in _check(env, "sentinel_providers")["providers"]}
    assert rows["openai"]["ready"] is True and rows["gemini"]["ready"] is False
    assert rows["openai"]["key_env"] == "OPENAI_API_KEY" and SECRET not in json.dumps(env)
    assert set(rows) == {"claude", "claude_code", "openai", "gemini", "openai_compatible"}


def test_paths_outside_the_root_are_refused(tmp_path):
    with pytest.raises(ToolError, match="outside the data root"):
        tools.list_candidates("../../etc")
    with pytest.raises(ToolError, match="outside the data root"):
        tools.vet_lightcurve(csv_path=str(tmp_path / "x.csv"))


def test_run_pipeline_csv_probes_only(tmp_path, monkeypatch, arrays):
    """A full run on a CSV inside the root: Probes only by default, so no AI provider is called."""
    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    rows = ["time,flux,flux_err"] + [f"{t},{f},{e}" for t, f, e in zip(arrays["time"], arrays["flux"], arrays["flux_err"])]
    (tmp_path / "lc.csv").write_text("\n".join(rows))
    (tmp_path / "panel.toml").write_text(
        '[run]\nname = "tool-test"\nmin_points = 100\n[search]\nfap_trials = 0\nfit_transits = false\n'
        '[[reviewers]]\ntype = "simulated"\nid = "volunteer-typical"\n'
        '[[reviewers]]\ntype = "openai"\nid = "gpt-skeptic"\nmodel = "m"\n')
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)

    def no_network(*a, **k):
        raise AssertionError("a Sentinel was called without sentinels=True")

    monkeypatch.setattr("setuhq.reviewers.http.post_json", no_network)
    env = tools.run_pipeline_csv("lc.csv", "out", target="pi Men", config_path="panel.toml")
    got = _check(env, "run_pipeline_csv")
    assert [r["id"] for r in got["reviewers"]] == ["volunteer-typical"]
    assert got["counts"]["subjects"] >= 1 and (tmp_path / "runs/mcp/out/manifest.json").exists()
    assert SECRET not in (tmp_path / "runs/mcp/out/manifest.json").read_text()
    with pytest.raises(ToolError):
        tools.run_pipeline_csv("lc.csv", "../escape", config_path="panel.toml")


def test_mcp_main_serves_stdio_by_default_and_http_on_request(monkeypatch):
    pytest.importorskip("mcp")
    import setuhq.mcp_server as M

    calls = []

    class Fake:
        def run(self, transport, **kw):
            calls.append((transport, kw))

    monkeypatch.setattr(M, "build_server", lambda *a, **k: Fake())
    assert M.main([]) == 0
    assert M.main(["--http", "127.0.0.1:8765"]) == 0
    assert calls[0] == ("stdio", {})
    assert calls[1][0] == "streamable-http"
    if M._server_class()[1] == 2:
        assert calls[1][1] == {"host": "127.0.0.1", "port": 8765}
    with pytest.raises(SystemExit):
        M.main(["--http", "nonsense"])


def test_tool_runs_never_overwrite_stored_results(tmp_path, monkeypatch, arrays):
    """A tool run goes to a new runs/mcp/<name>; the stored pi Men run, the data root and an existing run are refused."""
    import shutil

    monkeypatch.setenv("SETUHQ_ROOT", str(tmp_path))
    stored = tmp_path / "runs/tess-pi-men-s1"
    shutil.copytree(ROOT / RUN, stored, ignore=shutil.ignore_patterns("subjects", "fap_null"))
    before = {p.name: p.read_bytes() for p in stored.iterdir() if p.is_file()}
    rows = ["time,flux"] + [f"{t},{f}" for t, f in zip(arrays["time"], arrays["flux"])]
    (tmp_path / "lc.csv").write_text("\n".join(rows))
    (tmp_path / "panel.toml").write_text('[run]\nname = "t"\nmin_points = 100\n[search]\nfap_trials = 0\nfit_transits = false\n'
                                         '[[reviewers]]\ntype = "simulated"\nid = "volunteer-typical"\n')
    for bad in ("runs/tess-pi-men-s1", "../tess-pi-men-s1", ".", "", str(tmp_path / "abs"), "a/b"):
        with pytest.raises(ToolError, match="plain name"):
            tools.run_pipeline_csv("lc.csv", bad, config_path="panel.toml")
    tools.run_pipeline_csv("lc.csv", "first", config_path="panel.toml")
    with pytest.raises(ToolError, match="already exists"):
        tools.run_pipeline_csv("lc.csv", "first", config_path="panel.toml")
    assert {p.name: p.read_bytes() for p in stored.iterdir() if p.is_file()} == before  # untouched
    assert not (tmp_path / "manifest.json").exists() and not (tmp_path / "candidates.json").exists()
    with pytest.raises(ToolError):
        tools.run_pipeline_tess("261136679", "runs/tess-pi-men-s1")


def test_write_tool_hints_are_truthful(server):
    listed = {t.name: t.annotations for t in _run(server.list_tools)}
    for name in ("run_pipeline_csv", "run_pipeline_tess"):
        a = listed[name].model_dump(by_alias=True)
        assert a["readOnlyHint"] is False and a["idempotentHint"] is False and a["openWorldHint"] is True
        assert a["destructiveHint"] is False  # it only ever creates a new directory, refused if it exists
    assert listed["get_candidate"].model_dump(by_alias=True)["readOnlyHint"] is True


def test_http_mode_is_read_only_unless_allowed(monkeypatch):
    pytest.importorskip("mcp")
    import setuhq.mcp_server as M

    built = []
    real = M.build_server

    def capture(*a, **k):
        server = real(*a, **k)
        built.append((a, k, [t.name for t in _run(server.list_tools)]))
        server.run = lambda *x, **y: None
        return server

    monkeypatch.setattr(M, "build_server", capture)
    M.main(["--http", "8080"])
    args, kw, names = built[-1]
    assert args[0] == "127.0.0.1" and "run_pipeline_csv" not in names and "run_pipeline_tess" not in names
    assert "get_candidate" in names
    M.main(["--http", "8080", "--allow-writes"])
    assert "run_pipeline_csv" in built[-1][2] and built[-1][1]["allow_sentinels"] is False
    with pytest.raises(SystemExit):
        M.main(["--http", "8080", "--allow-sentinels"])  # Sentinels only inside a run: needs --allow-writes
    server = real(allow_writes=True, allow_sentinels=False)
    with pytest.raises(Exception, match="Sentinels are disabled"):
        _run(server.call_tool, "run_pipeline_csv", {"csv_path": "x.csv", "run_name": "x", "sentinels": True})


def test_tool_errors_do_not_reveal_the_data_root(server):
    with pytest.raises(Exception) as err:
        _run(server.call_tool, "list_candidates", {"run_dir": "runs/no-such-run"})
    assert str(ROOT) not in str(err.value) and "runs/no-such-run" in str(err.value)
    env = tools.search_catalogue("pi Men", limit=1)
    assert str(ROOT) not in json.dumps(env["provenance"])


def test_tool_runs_never_follow_a_link(tmp_path, monkeypatch):
    """A dangling symlink at the name, or a symlinked runs/mcp, cannot redirect a run outside runs/mcp."""
    import os

    data = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "runs/mcp").mkdir(parents=True)
    monkeypatch.setenv("SETUHQ_ROOT", str(data))
    os.symlink(outside / "gone", data / "runs/mcp/dangling")  # dangling: its target does not exist
    with pytest.raises(ToolError, match="already exists"):
        tools._new_run_dir("dangling")
    assert not (outside / "gone").exists()
    (data / "runs/mcp/dangling").unlink()
    (data / "runs/mcp").rmdir()
    os.symlink(outside, data / "runs/mcp")
    with pytest.raises(ToolError, match="is a link"):
        tools._new_run_dir("fresh")
    assert list(outside.iterdir()) == []
    (data / "runs/mcp").unlink()
    (data / "runs").rmdir()
    os.symlink(outside, data / "runs")
    with pytest.raises(ToolError, match="is a link"):
        tools._new_run_dir("fresh")
    assert list(outside.iterdir()) == []

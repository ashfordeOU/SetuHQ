"""The Claude Code plugin (manifests, slash commands, skills) and the example agent, offline."""

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from exoplan.tools import TOOLS

ROOT = Path(__file__).resolve().parents[1]
TOOL_NAMES = {fn.__name__ for fn, _ in TOOLS}


def _frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} has no front matter"
    meta = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, m.group(2)


def test_plugin_and_marketplace_manifests_are_valid():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert plugin["name"] == "exoplan" and re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"])
    assert plugin["description"] and plugin["license"] == "MIT"
    server = plugin["mcpServers"]["exoplan"]
    assert server["command"] == "exoplan-mcp" and server["env"]["EXOPLAN_ROOT"] == "${CLAUDE_PLUGIN_ROOT}"
    entry = next(p for p in market["plugins"] if p["name"] == plugin["name"])
    assert entry["source"] == "./" and entry["version"] == plugin["version"]
    assert re.fullmatch(r"[a-z0-9-]+", market["name"]) and market["owner"]["name"]
    # The server is declared once, by the plugin: no project .mcp.json to clash with it on install.
    assert not (ROOT / ".mcp.json").exists()
    # The entry point the manifests start is the one pyproject installs.
    assert 'exoplan-mcp = "exoplan.mcp_server:main"' in (ROOT / "pyproject.toml").read_text()


def test_slash_commands_use_only_real_tools():
    commands = sorted((ROOT / "commands").glob("*.md"))
    assert {c.stem for c in commands} == {"exoplan-vet", "exoplan-explain", "exoplan-sweep", "exoplan-catalogue",
                                         "exoplan-physics", "exoplan-benchmarks"}
    used = set()
    for path in commands:
        meta, body = _frontmatter(path)
        assert meta["description"] and meta["argument-hint"] and "$ARGUMENTS" in body
        named = set(re.findall(r"\*\*`([a-z_]+)`\*\*", body))
        assert named and named <= TOOL_NAMES, f"{path.name} names a tool the server does not have: {named - TOOL_NAMES}"
        used |= named
        if path.stem in ("exoplan-vet", "exoplan-explain", "exoplan-sweep"):
            assert "candidate" in body.lower() and "discovery" in body.lower()
    assert used == TOOL_NAMES  # every tool is reachable from a command


def test_skills_have_front_matter_and_honesty_rules():
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert {s.parent.name for s in skills} == {"vet-tess-target", "explain-candidate", "sector-sweep", "leaderboard-submission"}
    for path in skills:
        meta, body = _frontmatter(path)
        assert meta["name"] == path.parent.name and len(meta["description"]) > 60
        assert set(re.findall(r"`([a-z]+_[a-z_]+)`", body)) & TOOL_NAMES
        low = body.lower()
        assert path.parent.name == "leaderboard-submission" or "candidate" in low
        assert "never post" in low or "do not post" in low or "stop and ask" in low
        assert "superintelligence" not in low


def test_docs_name_every_tool():
    doc = (ROOT / "docs/MCP-INSTALL.md").read_text()
    for name in TOOL_NAMES:
        assert f"`{name}`" in doc
    for client in ("Claude Desktop", "Claude Code", "Cursor", "VS Code", "Codex CLI", "Gemini CLI"):
        assert f"### {client}" in doc
    readme = (ROOT / "README.md").read_text()
    assert "## AI providers" in readme and "## AI assistant (MCP, agents)" in readme
    assert readme.index("## AI assistant (MCP, agents)") < readme.index("## Editions")
    assert "Only Claude has been benchmarked so far." in readme
    assert "superintelligence" not in readme.lower()


# ---------------------------------------------------------------- the example agent


def _load_agent():
    spec = importlib.util.spec_from_file_location("vet_agent", ROOT / "examples/agents/vet_agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agent_gate_keeps_a_human_in_the_loop():
    agent = _load_agent()
    never = lambda q: pytest.fail("a read-only tool must not ask")  # noqa: E731
    for fn, read_only in TOOLS:
        if read_only:
            assert agent.gate(f"mcp__exoplan__{fn.__name__}", {}, never)[0]
    asked = []
    ok, why = agent.gate("mcp__exoplan__run_pipeline_csv", {"csv_path": "x.csv"}, lambda q: asked.append(q) or False)
    assert not ok and asked and why == "declined by a person"
    assert agent.gate("mcp__exoplan__run_pipeline_csv", {}, lambda q: True) == (True, "approved by a person")
    for outward in ("Bash", "WebFetch", "mcp__exofop__submit", "mcp__slack__post_message", "mcp__exoplan__submit_to_exofop"):
        ok, why = agent.gate(outward, {}, lambda q: True)  # even a yes does not let the agent act outward
        assert not ok and "person must do this" in why


def test_agent_runs_end_to_end_with_a_fake_sdk(tmp_path, monkeypatch):
    """The agent loop, the provenance log and the approval gate, with the SDK replaced by a fake (no model call)."""
    agent = _load_agent()
    fake = types.ModuleType("claude_agent_sdk")

    class Opts:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class TextBlock:
        def __init__(self, text):
            self.text = text

    class AssistantMessage:
        def __init__(self, content):
            self.content = content

    class ResultMessage:
        subtype, total_cost_usd, model_usage = "success", 0.0, {"claude-test": {}}

    class Allow:
        pass

    class Deny:
        def __init__(self, message):
            self.message = message

    seen = {}

    async def query(prompt, options):
        seen["options"] = options
        async for _ in prompt:
            pass
        # The model calls a read-only tool (hooks fire), then asks for an outward action (refused).
        await options.hooks["PreToolUse"][0].hooks[0]({"tool_name": "mcp__exoplan__get_candidate",
                                                        "tool_input": {"candidate_id": "c"}}, "t1", None)
        await options.hooks["PostToolUse"][0].hooks[0]({"tool_name": "mcp__exoplan__get_candidate",
                                                         "tool_response": {"result": {"passed": True}}}, "t1", None)
        seen["outward"] = await options.can_use_tool("WebFetch", {"url": "https://exofop.example"}, None)
        yield AssistantMessage([TextBlock("A candidate on a 6.27 d period.")])
        yield ResultMessage()

    fake.ClaudeAgentOptions, fake.TextBlock, fake.AssistantMessage, fake.ResultMessage = Opts, TextBlock, AssistantMessage, ResultMessage
    fake.PermissionResultAllow, fake.PermissionResultDeny, fake.query = Allow, Deny, query
    fake.HookMatcher = lambda hooks: types.SimpleNamespace(hooks=hooks)
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake)

    import anyio

    log = tmp_path / "prov.jsonl"
    args = types.SimpleNamespace(candidate="tess-fa3483ce6f83-000", csv=None, target="custom", run_dir="runs/tess-pi-men-s1",
                                 log=str(log), max_turns=4, model=None)
    report = anyio.run(agent.run_agent, args)
    assert report.startswith(agent.BANNER) and "candidate, not a discovery" in report
    opts = seen["options"]
    assert opts.tools == [] and all(t.startswith("mcp__exoplan__") for t in opts.allowed_tools)
    assert "mcp__exoplan__run_pipeline_csv" not in opts.allowed_tools  # writing tools ask first
    assert opts.mcp_servers["exoplan"]["args"] == ["-m", "exoplan.mcp_server"]
    assert isinstance(seen["outward"], Deny)
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert [e["event"] for e in events] == ["task", "tool_call", "tool_result", "permission", "result", "report"]
    assert all(e["at"] for e in events) and events[2]["output"] == {"result": {"passed": True}}
    assert events[3]["allowed"] is False

#!/usr/bin/env python3
"""EXAMPLE: an agent that vets one SetuHQ candidate end to end, through the exoplan MCP server.

This is an example of wiring, not part of SetuHQ's pipeline, and its output is not a result. It uses the
Claude Agent SDK (``pip install -e '.[agents]'``; it drives the Claude Code CLI, so ``claude`` must be on
PATH and signed in). Any other tool-calling model can do the same through the MCP server
(docs/MCP-INSTALL.md); only the agent loop here is Claude's.

    python examples/agents/vet_agent.py --candidate tess-fa3483ce6f83-000
    python examples/agents/vet_agent.py --csv my_lightcurve.csv --target "TIC 123"

What it does:

1. Starts ``exoplan-mcp`` (stdio) and gives the agent SetuHQ's tools, and no others: no shell, no file
   writes, no web. Its conclusions come from SetuHQ's own code and stored results.
2. Logs every tool call and every result, as JSON lines, to a provenance log (``--log``), with the time.
3. Keeps a human in the loop. Read-only tools run freely. A tool that writes (a pipeline run) asks you
   first. Anything outward-facing (posting, submitting, sending, a web request) is refused: the agent
   never takes an action outside this computer; a person reviews the report and decides.

An agent's conclusions are candidates, not discoveries. The report says so at the top, and a planet is
confirmed only by follow-up observations, by people.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

SERVER = "exoplan"
BANNER = ("EXAMPLE AGENT OUTPUT. A candidate, not a discovery: this is an AI agent's reading of SetuHQ's tools, "
          "unreviewed. Confirming a planet needs follow-up observations by people.")

# What the agent may do without asking: the read-only exoplan tools. Writing tools need a yes from a person.
def _tool_sets():
    from exoplan.tools import TOOLS

    read_only = {f"mcp__{SERVER}__{fn.__name__}" for fn, ro in TOOLS if ro}
    writes = {f"mcp__{SERVER}__{fn.__name__}" for fn, ro in TOOLS if not ro}
    return read_only, writes


OUTWARD = ("submit", "post", "send", "publish", "upload", "email", "exofop", "webfetch", "websearch", "bash", "push")


def gate(tool: str, tool_input: dict, ask) -> tuple[bool, str]:
    """The human-in-the-loop rule for one tool call: (allowed, why).

    * a read-only exoplan tool: allowed;
    * an exoplan tool that writes (a pipeline run): allowed only if ``ask`` (a person) says yes;
    * anything outward-facing or outside the exoplan server: refused, whatever ``ask`` would say.
    """
    read_only, writes = _tool_sets()
    low = tool.lower()
    if tool in read_only:
        return True, "read-only SetuHQ tool"
    if any(word in low for word in OUTWARD) or not tool.startswith(f"mcp__{SERVER}__"):
        return False, "outward-facing or not a SetuHQ tool: a person must do this, not the agent"
    if tool in writes:
        if ask(f"The agent wants to run {tool} with {json.dumps(tool_input)}. Allow? [y/N] "):
            return True, "approved by a person"
        return False, "declined by a person"
    return False, "unknown tool"


class ProvenanceLog:
    """Every tool call and result, one JSON object per line, appended as they happen."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields) -> None:
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
        with self.path.open("a") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")


def task_prompt(args) -> str:
    if args.candidate:
        what = (f"Vet candidate {args.candidate} of the stored run {args.run_dir}. Call get_candidate, then "
                "benchmark_results for how reliable the panel is, and get_star for the host if it is in the catalogue.")
    else:
        what = (f"Vet the light curve {args.csv} (target {args.target}). Call vet_lightcurve, then fit_transit on the "
                "dip it vets and compute_fap (at most 200 trials) on the periodic signal.")
    return (f"{what}\n\nWrite a short report: what the signal is (depth, duration, period, SNR, FAP as labelled), "
            "what the vetting flags say, what the reviewers said (Sentinels are AI models and Probes are detectors, "
            "not people), and what would rule it in or out. Quote numbers only from tool results, with the honesty "
            "labels they carry. Call it a candidate, never a discovery or a planet. Do not post, submit or send "
            "anything.")


async def run_agent(args) -> str:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        HookMatcher,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        TextBlock,
        query,
    )

    log = ProvenanceLog(args.log)
    read_only, writes = _tool_sets()

    def ask(question: str) -> bool:
        return input(question).strip().lower() in ("y", "yes")

    async def can_use_tool(tool, tool_input, context):
        ok, why = gate(tool, tool_input, ask)
        log.write("permission", tool=tool, input=tool_input, allowed=ok, why=why)
        return PermissionResultAllow() if ok else PermissionResultDeny(message=why)

    async def before(hook_input, tool_use_id, context):
        log.write("tool_call", tool=hook_input.get("tool_name"), input=hook_input.get("tool_input"), id=tool_use_id)
        return {}

    async def after(hook_input, tool_use_id, context):
        log.write("tool_result", tool=hook_input.get("tool_name"), output=hook_input.get("tool_response"), id=tool_use_id)
        return {}

    options = ClaudeAgentOptions(
        mcp_servers={SERVER: {"type": "stdio", "command": sys.executable, "args": ["-m", "exoplan.mcp_server"],
                              "env": {"EXOPLAN_ROOT": str(ROOT), "PYTHONPATH": str(ROOT / "src")}}},
        tools=[],                              # no built-in tools: no shell, no file edits, no web
        allowed_tools=sorted(read_only),       # these run without asking; the rest go through can_use_tool
        can_use_tool=can_use_tool,
        hooks={"PreToolUse": [HookMatcher(hooks=[before])], "PostToolUse": [HookMatcher(hooks=[after])]},
        system_prompt=("You vet transit candidates with SetuHQ's tools. Every number you report comes from a tool "
                       "result. An agent's conclusion is a candidate, not a discovery. Never take an outward-facing "
                       "action; a person decides what is shared."),
        max_turns=args.max_turns,
        model=args.model,
        cwd=str(ROOT),
    )
    prompt = task_prompt(args)
    log.write("task", prompt=prompt, model=args.model or "the CLI's default")
    report = []
    # can_use_tool needs streaming input: the prompt is sent as one message from an async generator.
    async def messages():
        yield {"type": "user", "message": {"role": "user", "content": prompt}}

    async for message in query(prompt=messages(), options=options):
        if isinstance(message, AssistantMessage):
            report += [b.text for b in message.content if isinstance(b, TextBlock)]
        elif isinstance(message, ResultMessage):
            log.write("result", subtype=message.subtype, cost_usd=getattr(message, "total_cost_usd", None),
                      model_usage=getattr(message, "model_usage", None))
    text = BANNER + "\n\n" + "\n".join(report).strip()
    log.write("report", text=text)
    return text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--candidate", help="a candidate id from the stored run (see list_candidates)")
    what.add_argument("--csv", help="a CSV light curve under the data root: time, flux[, flux_err]")
    parser.add_argument("--target", default="custom", help="the target's name, for --csv")
    parser.add_argument("--run-dir", default="runs/tess-pi-men-s1")
    parser.add_argument("--log", default="runs/agent/provenance.jsonl", help="where the tool calls and results go")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--model", default=None, help="model for the agent (default: the Claude Code CLI's)")
    args = parser.parse_args(argv)
    try:
        import anyio
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        print("This example needs the Claude Agent SDK: pip install -e '.[agents]'", file=sys.stderr)
        return 2
    print(anyio.run(run_agent, args))
    print(f"\nprovenance log: {args.log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

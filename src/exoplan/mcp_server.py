"""``exoplan-mcp``: SetuHQ as a Model Context Protocol server.

Every tool is a function in :mod:`exoplan.tools`, registered as it is: the server holds no logic of its own.
Each returns JSON with the result, its provenance (code version, the stored files read and their SHA-256)
and honesty labels (a candidate is not a discovery; Sentinels are AI models, not people).

    exoplan-mcp                          # stdio (what Claude Desktop, Claude Code, Cursor and others start)
    exoplan-mcp --http 127.0.0.1:8080    # streamable HTTP at http://127.0.0.1:8080/mcp, for self-hosting

Install with ``pip install -e '.[mcp]'``. ``EXOPLAN_ROOT`` sets the data root (default: this checkout); no tool
reads or writes outside it. Per-client set-up: docs/MCP-INSTALL.md.
"""

from __future__ import annotations

import argparse
import functools
import sys

from exoplan import __version__
from exoplan.tools import TOOLS, ToolError

NAME = "exoplan"
INSTRUCTIONS = (
    "SetuHQ (exoplan) searches public NASA TESS light curves for transits with a reviewer panel of Sentinels "
    "(AI models; Claude by default, other providers labelled) and Probes (deterministic detectors), then vets "
    "and fits each dip. Call these tools instead of estimating: they run SetuHQ's own code or read its stored, "
    "reviewed results. Every answer carries provenance and honesty labels; keep them when you report. "
    "Anything SetuHQ finds is a candidate, not a discovery. Do not submit, post or send anything outward "
    "without the user's explicit approval."
)


def _server_class():
    """The SDK's server class: MCPServer (mcp 2.x) or FastMCP (mcp 1.x)."""
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer, 2
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("exoplan-mcp needs the MCP SDK: pip install -e '.[mcp]'") from exc
        return FastMCP, 1


def _sdk_tool_error(major: int):
    if major == 2:
        from mcp.server.mcpserver.exceptions import ToolError
    else:
        from mcp.server.fastmcp.exceptions import ToolError
    return ToolError


def _expose(fn, tool_error):
    """The tool as it is, except that a refused request (a bad path, a missing file, an argument out of range)
    reaches the model as the SDK's tool error with its message, rather than as a bare crash."""
    @functools.wraps(fn)
    def tool(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ToolError, ValueError, FileNotFoundError) as exc:
            raise tool_error(str(exc)) from exc

    return tool


def build_server(host: str = "127.0.0.1", port: int = 8080):
    """The server with every tool of :data:`exoplan.tools.TOOLS` registered (name = function name)."""
    from mcp.types import ToolAnnotations

    cls, major = _server_class()
    tool_error = _sdk_tool_error(major)
    kwargs = {"instructions": INSTRUCTIONS}
    if major == 1:  # FastMCP takes the HTTP address in its settings
        kwargs |= {"host": host, "port": port}
    server = cls(NAME, **kwargs)
    for fn, read_only in TOOLS:
        annotations = ToolAnnotations.model_validate({
            "title": fn.__name__.replace("_", " "),
            "readOnlyHint": read_only,
            "destructiveHint": False,
            "idempotentHint": read_only,
            "openWorldHint": fn.__name__ == "run_pipeline_tess",  # the only tool that reaches the network (MAST)
        })
        server.add_tool(_expose(fn, tool_error), name=fn.__name__, description=(fn.__doc__ or "").strip(), annotations=annotations)
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="exoplan-mcp", description="SetuHQ (exoplan) as an MCP server.")
    parser.add_argument("--http", metavar="HOST:PORT",
                        help="serve streamable HTTP at http://HOST:PORT/mcp instead of stdio (self-hosting only)")
    parser.add_argument("--list-tools", action="store_true", help="print the tool names and exit")
    parser.add_argument("--version", action="version", version=f"exoplan-mcp {__version__}")
    args = parser.parse_args(argv)
    if args.list_tools:
        for fn, read_only in TOOLS:
            print(f"{fn.__name__}{'' if read_only else '  (writes a run directory)'}")
        return 0
    if args.http:
        host, _, port = args.http.rpartition(":")
        if not host or not port.isdigit():
            parser.error("--http takes HOST:PORT, e.g. 127.0.0.1:8080")
        server = build_server(host, int(port))
        if _server_class()[1] == 1:
            server.run("streamable-http")
        else:
            server.run("streamable-http", host=host, port=int(port))
        return 0
    build_server().run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())

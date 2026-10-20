"""``setuhq-mcp``: SetuHQ as a Model Context Protocol server.

Every tool is a function in :mod:`setuhq.tools`, registered as it is: the server adds no science of its own,
only who may call what. Each tool returns JSON with the result, its provenance (code version, the stored files
read and their SHA-256) and honesty labels (a candidate is not a discovery; Sentinels are AI models, not people).

    setuhq-mcp                          # stdio (what Claude Desktop, Claude Code, Cursor and others start)
    setuhq-mcp --http 8080              # streamable HTTP at http://127.0.0.1:8080/mcp: read-only tools only
    setuhq-mcp --http 8080 --allow-writes --allow-sentinels   # also pipeline runs, and Sentinels in them

Over stdio the server is the user's own process, so every tool is there. Over HTTP it has no
authentication, so by default it binds to 127.0.0.1 and leaves out the tools that write (pipeline runs);
``--allow-writes`` adds them, and Sentinels (which may call a paid AI API) need ``--allow-sentinels`` too.

Install with ``pip install -e '.[mcp]'``. ``SETUHQ_ROOT`` sets the data root (default: this checkout); no tool
reads or writes outside it, and error messages give paths relative to it. Set-up: docs/MCP-INSTALL.md.
"""

from __future__ import annotations

import argparse
import functools
import sys

from setuhq import __version__
from setuhq.tools import TOOLS, ToolError, root

NAME = "setuhq"
INSTRUCTIONS = (
    "SetuHQ searches public NASA TESS light curves for transits with a reviewer panel of Sentinels "
    "(AI models; Claude by default, other providers labelled) and Probes (deterministic detectors), then vets "
    "and fits each dip. Call these tools instead of estimating: they run SetuHQ's own code or read its stored, "
    "reviewed results. Every answer carries provenance and honesty labels; keep them when you report. "
    "Anything SetuHQ finds is a candidate, not a discovery. Do not submit, post or send anything outward "
    "without the user's explicit approval."
)
DEFAULT_HOST = "127.0.0.1"


def _server_class():
    """The SDK's server class: MCPServer (mcp 2.x) or FastMCP (mcp 1.x)."""
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer, 2
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("setuhq-mcp needs the MCP SDK: pip install -e '.[mcp]'") from exc
        return FastMCP, 1


def _sdk_tool_error(major: int):
    if major == 2:
        from mcp.server.mcpserver.exceptions import ToolError as SdkToolError
    else:
        from mcp.server.fastmcp.exceptions import ToolError as SdkToolError
    return SdkToolError


def _scrub(message: str) -> str:
    """An error message with the absolute data root replaced, so a client never learns the server's paths."""
    base = str(root())
    return message.replace(base + "/", "").replace(base, "<data root>")


def _expose(fn, tool_error, *, allow_sentinels: bool = True):
    """The tool as it is, except that (a) a refused request reaches the model as the SDK's tool error with a
    message that holds no absolute path, and (b) without ``allow_sentinels`` a call asking for Sentinels is
    refused before anything runs."""
    @functools.wraps(fn)
    def tool(*args, **kwargs):
        if kwargs.get("sentinels") and not allow_sentinels:
            raise tool_error("Sentinels are disabled on this server (they may call a paid AI API); "
                             "its operator can start it with --allow-sentinels")
        try:
            return fn(*args, **kwargs)
        except (ToolError, ValueError, FileNotFoundError) as exc:
            raise tool_error(_scrub(str(exc))) from None

    return tool


def build_server(host: str = DEFAULT_HOST, port: int = 8080, *, allow_writes: bool = True, allow_sentinels: bool = True):
    """The server with the tools of :data:`setuhq.tools.TOOLS` registered (name = function name).

    ``allow_writes=False`` leaves out the tools that write a run directory; ``allow_sentinels=False`` keeps them
    to Probes. Tool annotations say what each does: the write tools only ever create a new directory
    (``runs/mcp/<run_name>``, refused if it exists), so they are not destructive, and they reach outside this
    computer (MAST, and a provider's API when Sentinels run).
    """
    from mcp.types import ToolAnnotations

    cls, major = _server_class()
    tool_error = _sdk_tool_error(major)
    kwargs = {"instructions": INSTRUCTIONS}
    if major == 1:  # FastMCP takes the HTTP address in its settings
        kwargs |= {"host": host, "port": port}
    server = cls(NAME, **kwargs)
    for fn, read_only in TOOLS:
        if not read_only and not allow_writes:
            continue
        annotations = ToolAnnotations.model_validate({
            "title": fn.__name__.replace("_", " "),
            "readOnlyHint": read_only,
            "destructiveHint": False,       # nothing is overwritten or deleted: a run gets a new directory or is refused
            "idempotentHint": read_only,    # a second run with the same name is refused, so writes are not idempotent
            "openWorldHint": not read_only,  # MAST downloads; a provider's API when Sentinels are allowed and asked for
        })
        server.add_tool(_expose(fn, tool_error, allow_sentinels=allow_sentinels), name=fn.__name__,
                        description=(fn.__doc__ or "").strip(), annotations=annotations)
    return server


def _address(value: str) -> tuple[str, int]:
    """'8080' (bound to 127.0.0.1) or 'HOST:PORT'."""
    host, _, port = value.rpartition(":")
    if not port.isdigit():
        raise ValueError(value)
    return host or DEFAULT_HOST, int(port)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="setuhq-mcp", description="SetuHQ as an MCP server.")
    parser.add_argument("--http", metavar="[HOST:]PORT",
                        help="serve streamable HTTP at http://HOST:PORT/mcp instead of stdio (self-hosting; HOST "
                             "defaults to 127.0.0.1). It has no authentication: read-only tools only, unless allowed below")
    parser.add_argument("--allow-writes", action="store_true",
                        help="with --http: also expose the pipeline-run tools (each writes a new runs/mcp/<name>)")
    parser.add_argument("--allow-sentinels", action="store_true",
                        help="with --http: let pipeline runs use Sentinels, which may call a paid AI API with this "
                             "server's keys")
    parser.add_argument("--list-tools", action="store_true", help="print the tool names and exit")
    parser.add_argument("--version", action="version", version=f"setuhq-mcp {__version__}")
    args = parser.parse_args(argv)
    if args.list_tools:
        for fn, read_only in TOOLS:
            print(f"{fn.__name__}{'' if read_only else '  (writes a new run directory; over HTTP only with --allow-writes)'}")
        return 0
    if args.http:
        try:
            host, port = _address(args.http)
        except ValueError:
            parser.error("--http takes PORT or HOST:PORT, e.g. 8080 or 127.0.0.1:8080")
        if args.allow_sentinels and not args.allow_writes:
            parser.error("--allow-sentinels needs --allow-writes (Sentinels run only inside a pipeline run)")
        server = build_server(host, port, allow_writes=args.allow_writes, allow_sentinels=args.allow_sentinels)
        if _server_class()[1] == 1:
            server.run("streamable-http")
        else:
            server.run("streamable-http", host=host, port=port)
        return 0
    build_server().run("stdio")
    return 0


LEGACY_NOTICE = ("exoplan-mcp: this server is now 'setuhq-mcp'; the 'exoplan-mcp' alias is deprecated and will be removed "
                 "in a later release.")


def legacy_main(argv=None) -> int:
    """The deprecated ``exoplan-mcp`` command: one line on stderr (stdout is the MCP stream), then ``setuhq-mcp``."""
    print(LEGACY_NOTICE, file=sys.stderr)
    return main(argv)


if __name__ == "__main__":
    sys.exit(main())

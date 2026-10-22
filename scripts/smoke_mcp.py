#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Start an MCP server over stdio, initialize it and list its tools: the release smoke test of setuhq-mcp.

Plain JSON-RPC over the server's stdin and stdout, standard library only, so it checks an installed command
(for example from a freshly installed wheel) without importing anything from the package.

    python3 scripts/smoke_mcp.py --min-tools 16 -- .venv/bin/setuhq-mcp
    python3 scripts/smoke_mcp.py --min-tools 16 -- uvx --from 'setuhq[mcp]' setuhq mcp
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading


def _read(proc: subprocess.Popen, want_id: int, timeout: float) -> dict:
    box: dict = {}

    def run():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == want_id:
                box["msg"] = msg
                return

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if "msg" not in box:
        raise TimeoutError(f"no answer to request {want_id} within {timeout:.0f} s")
    return box["msg"]


def smoke(command: list[str], timeout: float = 60.0) -> list[str]:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)
    try:
        def send(msg: dict) -> None:
            proc.stdin.write(json.dumps(msg) + "\n")
            proc.stdin.flush()

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "setuhq-smoke", "version": "0"}}})
        init = _read(proc, 1, timeout)
        if "result" not in init:
            raise RuntimeError(f"initialize failed: {init}")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = _read(proc, 2, timeout)
        return [t["name"] for t in listed["result"]["tools"]]
    finally:
        proc.kill()
        proc.wait()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="initialize an MCP stdio server and list its tools")
    parser.add_argument("command", nargs="+", help="the server command, e.g. .venv/bin/setuhq-mcp")
    parser.add_argument("--min-tools", type=int, default=1)
    args = parser.parse_args(argv)
    names = smoke(args.command)
    print(f"{len(names)} tools: {', '.join(names)}")
    if len(names) < args.min_tools:
        print(f"FAIL: expected at least {args.min_tools} tools", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

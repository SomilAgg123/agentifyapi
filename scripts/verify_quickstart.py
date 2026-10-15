"""Prove the README example works: mount → crawl → approve → agent call."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "quickstart.db"
os.chdir(ROOT)
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ.setdefault("AGENTIFYAPI_DESCRIBER", "template")


def text_of(res: CallToolResult) -> str:
    block = res.content[0]
    assert isinstance(block, TextContent), f"expected text content, got {type(block).__name__}"
    return block.text


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def cli(*args: str) -> str:
    cmd = [sys.executable, "-m", "agentifyapi.cli", "--db", str(DB), *args]
    print("$ agentifyapi", " ".join(args), flush=True)
    out = subprocess.check_output(cmd, text=True, env={**os.environ, "PYTHONPATH": f"{ROOT}:{ROOT / 'src'}"})
    print(out, end="" if out.endswith("\n") else "\n", flush=True)
    return out


async def mcp_call(url: str, name: str, args: dict):
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool(name, args)
            return tools, res.isError, text_of(res)


def main() -> int:
    DB.unlink(missing_ok=True)
    from examples.quickstart import app

    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        for _ in range(100):
            try:
                httpx.get(f"{url}/mcp-admin/", timeout=1).raise_for_status()
                break
            except httpx.HTTPError:
                time.sleep(0.05)

        listed = cli("tools", "list")
        line = next(ln for ln in listed.splitlines() if ln.startswith("inventory.get_stock"))
        assert "disabled" in line and "enabled" not in line, line

        # Before approval: agents cannot see or call the tool.
        tools, err, text = asyncio.run(mcp_call(f"{url}/mcp", "list_tools", {"server": "inventory"}))
        assert tools == ["discover_servers", "list_tools", "get_tool_schema", "invoke_tool"]
        assert json.loads(text) == []
        print("before approval: agent sees 0 tools for inventory")

        cli("tools", "diff", "inventory.get_stock")
        cli("tools", "approve", "inventory.get_stock", "--by", "readme")
        cli("tools", "enable", "inventory.get_stock")

        tools, err, text = asyncio.run(
            mcp_call(f"{url}/mcp", "invoke_tool", {"tool": "inventory.get_stock", "args": {"sku": "KB-1"}})
        )
        assert not err, text
        assert json.loads(text) == {"sku": "KB-1", "on_hand": 42, "warehouse": "nyc"}, text
        print("after approval: agent called inventory.get_stock →", text.replace("\n", " "))
        print("quickstart verified")
        return 0
    finally:
        server.should_exit = True
        thread.join(5)
        DB.unlink(missing_ok=True)
        Path("audit.log").unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())

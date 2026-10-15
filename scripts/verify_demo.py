"""Prove the real demo works: boot `run_demo.py --keep`, then check what an agent and an owner see."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parent.parent
GW = "http://127.0.0.1:8000"


async def call(key, tool, args, path="/mcp"):
    async with streamablehttp_client(GW + path, headers={"x-api-key": key}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return res.isError, res.content[0].text


async def checks():
    results = []

    def check(name, ok, got):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"\n      got: {got}"))

    err, text = await call("demo-support-key", "discover_servers", {"query": "order"})
    got = json.loads(text)
    check("discovery ranks orders first", got[0] == {"server": "orders", "owner": "team-commerce", "tools": 2}, got)

    err, text = await call("demo-support-key", "list_tools", {"server": "users"})
    got = [t["tool"] for t in json.loads(text)]
    check("only approved+enabled tools are listed", got == ["users.get_user"], got)

    err, text = await call("demo-support-key", "invoke_tool",
                           {"tool": "orders.get_order", "args": {"order_id": 101}, "fields": ["id", "card_number"]})
    check("projection + card redaction", json.loads(text) == {"id": 101, "card_number": "[REDACTED:card]"}, text)

    err, text = await call("demo-readonly-key", "invoke_tool", {"tool": "users.get_user", "args": {"user_id": 1}})
    check("readonly role denied users.get_user", err and "not permitted" in text, text)

    err, text = await call("demo-support-key", "invoke_tool", {"tool": "users.search_users", "args": {}})
    check("unapproved tool unavailable", err and "not available" in text, text)

    err, text = await call("demo-support-key", "get_user", {"user_id": 2}, path="/servers/users/mcp")
    got = json.loads(text)
    check("per-server endpoint + email/phone redaction",
          got == {"id": 2, "name": "Alan Turing", "email": "[REDACTED:email]", "phone": "[REDACTED:phone]",
                  "tier": "basic"}, got)

    page = httpx.get(GW + "/admin/tools/users.search_users").text
    check("admin UI shows pending revision with approve button", "Approve pending" in page and "pending" in page,
          page[:200])

    last = json.loads((ROOT / "audit.log").read_text().splitlines()[-1])
    check("audit log records caller and redaction count",
          (last["tool"], last["caller"], last["redactions"]) == ("users.get_user", "support-agent", 2), last)
    return all(results)


def main():
    env = {**os.environ, "MCPIFY_DESCRIBER": "template"}
    demo = subprocess.Popen([sys.executable, str(ROOT / "scripts/run_demo.py"), "--keep"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(300):
            try:
                if httpx.get(GW + "/healthz", timeout=1).json()["enabled_tools"] == 3:
                    break
            except (httpx.HTTPError, ValueError):
                pass
            time.sleep(0.1)
        time.sleep(1)  # let run_demo's agent client finish so its audit lines land first
        ok = asyncio.run(checks())
    finally:
        demo.terminate()
        demo.wait(10)
    print("demo verified" if ok else "demo verification FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

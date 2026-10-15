"""Sample agent: discovers and calls a tool through the gateway using the MCP SDK client."""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent

URL = os.getenv("AGENTIFYAPI_URL", "http://127.0.0.1:8000/mcp")
KEY = os.getenv("AGENTIFYAPI_API_KEY", "demo-support-key")


def text_of(res: CallToolResult) -> str:
    block = res.content[0]
    assert isinstance(block, TextContent), f"expected text content, got {type(block).__name__}"
    return block.text


async def call(session, name, **args):
    res = await session.call_tool(name, args)
    text = text_of(res)
    print(f"\n>>> {name}({json.dumps(args)}){'  [ERROR]' if res.isError else ''}\n{text}")
    return None if res.isError else json.loads(text)


async def main():
    async with streamablehttp_client(URL, headers={"x-api-key": KEY}) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            print("meta-tools:", [t.name for t in (await session.list_tools()).tools])
            servers = await call(session, "discover_servers", query="order status")
            if not servers:
                return 1
            tools = await call(session, "list_tools", server=servers[0]["server"])
            await call(session, "get_tool_schema", tool="orders.get_order")
            await call(
                session,
                "invoke_tool",
                tool="orders.get_order",
                args={"order_id": 101},
                fields=["id", "status", "items.sku", "card_number", "shipping_note"],
            )
            await call(session, "invoke_tool", tool="users.get_user", args={"user_id": 1})
    return 0 if tools else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

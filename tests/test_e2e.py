"""End to end: run mock services, crawl, approve, then call through MCP over streamable HTTP."""

import json

import pytest
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client  # noqa: F401 (stable across 1.x)
from mcp.types import CallToolResult, TextContent

from agentifyapi import create_app, mount
from agentifyapi.config import PolicyConfig, ServiceConfig, Settings
from agentifyapi.crawler import crawl_all
from agentifyapi.registry import Registry


def text_of(res: CallToolResult) -> str:
    block = res.content[0]
    assert isinstance(block, TextContent), f"expected text content, got {type(block).__name__}"
    return block.text


pytestmark = pytest.mark.integration


async def _session_call(url, key, calls):
    out = []
    async with streamablehttp_client(url, headers={"x-api-key": key} if key else None) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out.append([t.name for t in (await s.list_tools()).tools])
            for name, args in calls:
                res = await s.call_tool(name, args)
                out.append((res.isError, text_of(res)))
    return out


async def test_gateway_end_to_end(tmp_path, serve):
    from examples.services.orders import app as orders_app

    with serve(orders_app) as orders_url:
        settings = Settings(
            database=str(tmp_path / "g.db"),
            audit_log=str(tmp_path / "audit.log"),
            services=[ServiceConfig(name="orders", owner="commerce", base_url=orders_url)],  # HTTP crawl
            policy=PolicyConfig.model_validate(
                {
                    "api_keys": {
                        "good": {"name": "support", "roles": ["support"]},
                        "weak": {"name": "bi", "roles": ["readonly"]},
                    },
                    "rules": [
                        {"tools": ["orders.*"], "roles": ["support"]},
                        {"tools": ["orders.get_order"], "roles": ["readonly"]},
                    ],
                }
            ),
        )
        reg = Registry(settings.database)
        assert crawl_all(reg, settings)["orders"]["new"]
        app = create_app(settings, reg)
        with serve(app) as gw:
            # nothing approved yet: invisible
            res = await _session_call(f"{gw}/mcp", "good", [("discover_servers", {})])
            assert json.loads(res[1][1]) == []

            for t in ("orders.get_order", "orders.create_order"):
                reg.approve(t, by="test")
                reg.set_enabled(t, True)

            res = await _session_call(
                f"{gw}/mcp",
                "good",
                [
                    ("discover_servers", {"query": "order"}),
                    ("list_tools", {"server": "orders"}),
                    ("get_tool_schema", {"tool": "orders.get_order"}),
                    (
                        "invoke_tool",
                        {"tool": "orders.get_order", "args": {"order_id": 101}, "fields": ["id", "card_number"]},
                    ),
                    ("invoke_tool", {"tool": "orders.list_orders", "args": {}}),  # not approved
                    (
                        "invoke_tool",
                        {
                            "tool": "orders.create_order",
                            "args": {"body": {"user_id": 2, "items": [{"sku": "Z", "qty": 1, "price_cents": 1}]}},
                        },
                    ),
                ],
            )
            assert res[0] == ["discover_servers", "list_tools", "get_tool_schema", "invoke_tool"]
            assert json.loads(res[1][1])[0]["server"] == "orders"
            assert {t["tool"] for t in json.loads(res[2][1])} == {"orders.get_order", "orders.create_order"}
            assert json.loads(res[3][1])["input_schema"]["required"] == ["order_id"]
            assert json.loads(res[4][1]) == {"id": 101, "card_number": "[REDACTED:card]"}
            assert res[5][0] and "not available" in res[5][1]
            assert json.loads(res[6][1])["user_id"] == 2

            # policy: readonly may read but not create; anonymous may do nothing
            res = await _session_call(
                f"{gw}/mcp",
                "weak",
                [
                    ("invoke_tool", {"tool": "orders.get_order", "args": {"order_id": 102}}),
                    ("invoke_tool", {"tool": "orders.create_order", "args": {"body": {"user_id": 1, "items": []}}}),
                ],
            )
            assert not res[1][0] and res[2][0] and "not permitted" in res[2][1]
            res = await _session_call(
                f"{gw}/mcp", None, [("invoke_tool", {"tool": "orders.get_order", "args": {"order_id": 1}})]
            )
            assert res[1][0]

            # discovery only shows what the caller's policy lets it invoke
            res = await _session_call(
                f"{gw}/mcp",
                "weak",
                [
                    ("discover_servers", {}),
                    ("list_tools", {"server": "orders"}),
                    ("get_tool_schema", {"tool": "orders.create_order"}),
                    ("get_tool_schema", {"tool": "orders.get_order"}),
                ],
            )
            assert json.loads(res[1][1]) == [{"server": "orders", "owner": "commerce", "tools": 1}]
            assert [t["tool"] for t in json.loads(res[2][1])] == ["orders.get_order"]
            assert res[3][0] and "not available" in res[3][1]
            assert not res[4][0] and json.loads(res[4][1])["tool"] == "orders.get_order"
            res = await _session_call(
                f"{gw}/mcp", None, [("discover_servers", {}), ("list_tools", {"server": "orders"})]
            )
            assert json.loads(res[1][1]) == [] and json.loads(res[2][1]) == []
            res = await _session_call(f"{gw}/servers/orders/mcp", "weak", [])
            assert res[0] == ["get_order"]
            res = await _session_call(f"{gw}/servers/orders/mcp", None, [])
            assert res[0] == []

            # direct per-server endpoint
            res = await _session_call(
                f"{gw}/servers/orders/mcp", "good", [("get_order", {"order_id": 102, "_fields": ["status"]})]
            )
            assert sorted(res[0]) == ["create_order", "get_order"]
            assert json.loads(res[1][1]) == {"status": "processing"}

            audit = [json.loads(line) for line in open(settings.audit_log)]
            assert any(e.get("decision") == "denied" and e["caller"] == "bi" for e in audit)


async def test_embed_mount(tmp_path, serve):
    app = FastAPI(title="inventory")

    @app.get("/stock/{sku}")
    def get_stock(sku: str) -> dict:
        """Units on hand for a SKU."""
        return {"sku": sku, "on_hand": 3, "contact": "ops@example.com"}

    mount(
        app,
        database=str(tmp_path / "e.db"),
        audit_log=None,
        auto_approve=True,
        policy=PolicyConfig(allow_anonymous=True),
    )
    with serve(app) as url:
        res = await _session_call(
            f"{url}/mcp",
            None,
            [
                ("list_tools", {"server": "inventory"}),
                ("invoke_tool", {"tool": "inventory.get_stock", "args": {"sku": "A-1"}}),
            ],
        )
        assert json.loads(res[1][1])[0]["tool"] == "inventory.get_stock"
        assert json.loads(res[2][1]) == {"sku": "A-1", "on_hand": 3, "contact": "[REDACTED:email]"}


async def test_embed_path_param_with_slash(tmp_path, serve):
    app = FastAPI(title="inventory")

    @app.get("/stock/{sku}")
    def get_stock(sku: str) -> dict:
        """Units on hand for a SKU."""
        return {"sku": sku, "on_hand": 3}

    mount(
        app,
        database=str(tmp_path / "s.db"),
        audit_log=None,
        auto_approve=True,
        admin_path=None,
        policy=PolicyConfig(allow_anonymous=True),
    )
    with serve(app) as url:
        res = await _session_call(
            f"{url}/mcp",
            None,
            [("invoke_tool", {"tool": "inventory.get_stock", "args": {"sku": "A/1 b?c"}})],
        )
        assert res[1][0] is False, res[1][1]
        assert json.loads(res[1][1]) == {"sku": "A/1 b?c", "on_hand": 3}


async def test_http_forwarding_encodes_path_params(tmp_path, monkeypatch):
    import httpx

    from agentifyapi.gateway import Gateway

    reg = Registry(str(tmp_path / "h.db"))
    app = FastAPI(title="inv")

    @app.get("/stock/{sku}")
    def get_stock(sku: str) -> dict:
        return {"sku": sku}

    from agentifyapi.crawler import crawl_service

    crawl_service(reg, ServiceConfig(name="inv", base_url="http://inv.local"), app=app)
    reg.approve("inv.get_stock", by="t")
    reg.set_enabled("inv.get_stock", True)
    seen = []
    gw = Gateway(reg, Settings(audit_log="", policy=PolicyConfig(allow_anonymous=True)))
    gw.transports.pop("inv", None)

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.raw_path)
        return httpx.Response(200, json={"ok": True})

    orig = httpx.AsyncClient

    class Patched(orig):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    import agentifyapi.gateway as gmod

    monkeypatch.setattr(gmod.httpx, "AsyncClient", Patched)
    await gw.invoke("inv.get_stock", {"sku": "A/1 b?c"}, None, None)
    assert seen == [b"/stock/A%2F1%20b%3Fc"]

"""End to end: run mock services, crawl, approve, then call through MCP over streamable HTTP."""
import json

from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client  # noqa: F401 (stable across 1.x)

from mcpify import create_app, mount
from mcpify.config import PolicyConfig, ServiceConfig, Settings
from mcpify.crawler import crawl_all
from mcpify.registry import Registry


async def _session_call(url, key, calls):
    out = []
    async with streamablehttp_client(url, headers={"x-api-key": key} if key else None) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            out.append([t.name for t in (await s.list_tools()).tools])
            for name, args in calls:
                res = await s.call_tool(name, args)
                out.append((res.isError, res.content[0].text))
    return out


async def test_gateway_end_to_end(tmp_path, serve):
    from examples.services.orders import app as orders_app
    with serve(orders_app) as orders_url:
        settings = Settings(
            database=str(tmp_path / "g.db"), audit_log=str(tmp_path / "audit.log"),
            services=[ServiceConfig(name="orders", owner="commerce", base_url=orders_url)],  # HTTP crawl
            policy=PolicyConfig.model_validate({
                "api_keys": {"good": {"name": "support", "roles": ["support"]},
                             "weak": {"name": "bi", "roles": ["readonly"]}},
                "rules": [{"tools": ["orders.*"], "roles": ["support"]},
                          {"tools": ["orders.get_order"], "roles": ["readonly"]}]}))
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

            res = await _session_call(f"{gw}/mcp", "good", [
                ("discover_servers", {"query": "order"}),
                ("list_tools", {"server": "orders"}),
                ("get_tool_schema", {"tool": "orders.get_order"}),
                ("invoke_tool", {"tool": "orders.get_order", "args": {"order_id": 101},
                                 "fields": ["id", "card_number"]}),
                ("invoke_tool", {"tool": "orders.list_orders", "args": {}}),     # not approved
                ("invoke_tool", {"tool": "orders.create_order",
                                 "args": {"body": {"user_id": 2, "items": [{"sku": "Z", "qty": 1, "price_cents": 1}]}}}),
            ])
            assert res[0] == ["discover_servers", "list_tools", "get_tool_schema", "invoke_tool"]
            assert json.loads(res[1][1])[0]["server"] == "orders"
            assert {t["tool"] for t in json.loads(res[2][1])} == {"orders.get_order", "orders.create_order"}
            assert json.loads(res[3][1])["input_schema"]["required"] == ["order_id"]
            assert json.loads(res[4][1]) == {"id": 101, "card_number": "[REDACTED:card]"}
            assert res[5][0] and "not available" in res[5][1]
            assert json.loads(res[6][1])["user_id"] == 2

            # policy: readonly may read but not create; anonymous may do nothing
            res = await _session_call(f"{gw}/mcp", "weak", [
                ("invoke_tool", {"tool": "orders.get_order", "args": {"order_id": 102}}),
                ("invoke_tool", {"tool": "orders.create_order", "args": {"body": {"user_id": 1, "items": []}}})])
            assert not res[1][0] and res[2][0] and "not permitted" in res[2][1]
            res = await _session_call(f"{gw}/mcp", None, [("invoke_tool", {"tool": "orders.get_order", "args": {"order_id": 1}})])
            assert res[1][0]

            # direct per-server endpoint
            res = await _session_call(f"{gw}/servers/orders/mcp", "good",
                                      [("get_order", {"order_id": 102, "_fields": ["status"]})])
            assert sorted(res[0]) == ["create_order", "get_order"]
            assert json.loads(res[1][1]) == {"status": "processing"}

            audit = [json.loads(l) for l in open(settings.audit_log)]
            assert any(e.get("decision") == "denied" and e["caller"] == "bi" for e in audit)


async def test_embed_mount(tmp_path, serve):
    app = FastAPI(title="inventory")

    @app.get("/stock/{sku}")
    def get_stock(sku: str) -> dict:
        """Units on hand for a SKU."""
        return {"sku": sku, "on_hand": 3, "contact": "ops@example.com"}

    mount(app, database=str(tmp_path / "e.db"), audit_log=None, auto_approve=True,
          policy=PolicyConfig(allow_anonymous=True))
    with serve(app) as url:
        res = await _session_call(f"{url}/mcp", None, [
            ("list_tools", {"server": "inventory"}),
            ("invoke_tool", {"tool": "inventory.get_stock", "args": {"sku": "A-1"}})])
        assert json.loads(res[1][1])[0]["tool"] == "inventory.get_stock"
        assert json.loads(res[2][1]) == {"sku": "A-1", "on_hand": 3, "contact": "[REDACTED:email]"}

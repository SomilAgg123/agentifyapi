"""Embed mode: add a governed MCP endpoint to an existing FastAPI app.

    from mcpify import mount
    app = FastAPI()
    ...routes...
    mount(app)          # -> /mcp, /servers/<name>/mcp, /mcp-admin

Routes are introspected in-process at startup and calls are dispatched in-process
(ASGI transport), so no network hop and no separate deployment. Tools still start
disabled: approve/enable them with the CLI (`mcpify --db <path> tools ...`) or /mcp-admin.
"""
from __future__ import annotations

import contextlib

import httpx
from fastapi import FastAPI

from .admin import admin_router
from .config import PolicyConfig, ServiceConfig, Settings
from .crawler import crawl_service
from .gateway import Gateway
from .registry import Registry


def mount(app: FastAPI, *, name: str | None = None, owner: str | None = None, database: str = "mcpify.db",
          policy: PolicyConfig | None = None, prefix: str = "", admin_path: str | None = "/mcp-admin",
          auto_approve: bool = False, redact_pii: bool = True, audit_log: str | None = "audit.log") -> Gateway:
    """Attach mcpify to `app`. `auto_approve=True` is for local development only."""
    server_name = name or (app.title or "app").lower().replace(" ", "_")
    settings = Settings(database=database, audit_log=audit_log or "", redact_pii=redact_pii,
                        policy=policy or PolicyConfig(),
                        services=[ServiceConfig(name=server_name, owner=owner)])
    reg = Registry(database)
    gw = Gateway(reg, settings)
    gw.transports[server_name] = httpx.ASGITransport(app=app)

    gw_routes = gw.routes(prefix)
    if admin_path:
        app.include_router(admin_router(reg, gw.audit), prefix=admin_path, include_in_schema=False)
    app.router.routes.extend(gw_routes)

    original = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(a):
        # crawl after all routes are registered, excluding our own endpoints
        report = crawl_service(reg, settings.services[0], app=app)
        if auto_approve:
            for t in report["new"] + report["changed"]:
                reg.approve(t, by="auto_approve")
                reg.set_enabled(t, True)
        async with original(a) as state, gw.lifespan():
            yield state

    app.router.lifespan_context = lifespan
    app.state.mcpify = gw
    return gw

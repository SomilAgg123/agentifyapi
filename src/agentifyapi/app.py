"""Standalone gateway app: many services -> one governed MCP endpoint + admin UI."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI

from .admin import admin_router
from .config import Settings, load_settings
from .crawler import crawl_forever
from .gateway import Gateway
from .registry import Registry


def create_app(settings: Settings | str | None = None, registry: Registry | None = None) -> FastAPI:
    if not isinstance(settings, Settings):
        settings = load_settings(settings)
    reg = registry or Registry(settings.database)
    gw = Gateway(reg, settings)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(crawl_forever(reg, settings)) if settings.crawl_interval_seconds else None
        async with gw.lifespan():
            yield
        if task:
            task.cancel()

    app = FastAPI(title="agentifyapi gateway", lifespan=lifespan)
    app.state.gateway, app.state.registry = gw, reg
    app.router.routes.extend(gw.routes())
    app.include_router(admin_router(reg, gw.audit, settings.admin), prefix="/admin")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "servers": len(reg.servers()), "enabled_tools": len(reg.tools(enabled_only=True))}

    return app

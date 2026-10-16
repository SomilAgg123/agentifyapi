"""Embed mode: add a governed MCP endpoint to an existing FastAPI app.

    from agentifyapi import mount
    app = FastAPI()
    ...routes...
    mount(app)          # -> /mcp, /servers/<name>/mcp, /mcp-admin

Routes are introspected in-process at startup and calls are dispatched in-process
(ASGI transport), so no network hop and no separate deployment. Tools still start
disabled: approve/enable them with the CLI (`agentifyapi --db <path> tools ...`) or /mcp-admin.
"""

from __future__ import annotations

import contextlib
from typing import Any
from urllib.parse import quote, unquote

import httpx
from fastapi import FastAPI
from starlette.routing import Match

from .admin import admin_router
from .config import AdminConfig, PolicyConfig, ServiceConfig, Settings
from .crawler import crawl_service
from .gateway import Gateway
from .registry import Registry

_FLAG = "agentifyapi.dispatch"


def _segment_path(raw_path: bytes) -> str:
    """Decode a raw path segment by segment, keeping '/' and '%' inside a segment encoded."""
    return "/".join(quote(unquote(seg), safe="") for seg in raw_path.decode("latin-1").split("/"))


def _install_slash_routing(app: FastAPI) -> None:
    """Let in-process dispatch deliver path params that contain '/'.

    The gateway percent-encodes path params ('A/1' -> 'A%2F1'), but Starlette routes on the decoded
    path, where that becomes two segments and 404s. For requests from our own transport only, match
    routes against the segment-encoded path and decode the captured params. This runs inside the
    app's middleware stack (we wrap the router), so the app's own middleware still applies.
    """
    router = app.router
    inner = router.middleware_stack

    async def routed(scope, receive, send):
        raw = scope.get("raw_path") or b""
        if scope.get(_FLAG) and scope["type"] == "http" and b"%2f" in raw.lower():
            probe: dict[str, Any] = {**scope, "path": scope.get("root_path", "") + _segment_path(raw)}
            for route in router.routes:
                match, child = route.matches(probe)
                if match == Match.FULL:
                    params = {
                        k: unquote(v) if isinstance(v, str) else v for k, v in child.get("path_params", {}).items()
                    }
                    scope.update(child)
                    scope["path_params"] = params
                    await route.handle(scope, receive, send)
                    return
        await inner(scope, receive, send)

    router.middleware_stack = routed


def _flagged(app: FastAPI):
    async def asgi(scope, receive, send):
        scope = {**scope, _FLAG: True}
        await app(scope, receive, send)

    return asgi


def mount(
    app: FastAPI,
    *,
    name: str | None = None,
    owner: str | None = None,
    database: str = "agentifyapi.db",
    policy: PolicyConfig | None = None,
    prefix: str = "",
    admin_path: str | None = "/mcp-admin",
    auto_approve: bool = False,
    redact_pii: bool = True,
    audit_log: str | None = "audit.log",
    admin_password: str | None = None,
    admin_username: str = "admin",
    admin_allow_remote: bool = False,
) -> Gateway:
    """Attach agentifyapi to `app`. `auto_approve=True` is for local development only.

    The admin UI requires HTTP Basic auth when `admin_password` (or env AGENTIFYAPI_ADMIN_PASSWORD)
    is set; otherwise it only answers loopback clients unless `admin_allow_remote=True` (dev only).
    """
    server_name = name or (app.title or "app").lower().replace(" ", "_")
    settings = Settings(
        database=database,
        audit_log=audit_log or "",
        redact_pii=redact_pii,
        policy=policy or PolicyConfig(),
        services=[ServiceConfig(name=server_name, owner=owner)],
        admin=AdminConfig(username=admin_username, password=admin_password, insecure_allow_remote=admin_allow_remote),
    )
    reg = Registry(database)
    gw = Gateway(reg, settings)
    gw.transports[server_name] = httpx.ASGITransport(app=_flagged(app))
    _install_slash_routing(app)

    gw_routes = gw.routes(prefix)
    if admin_path:
        app.include_router(admin_router(reg, gw.audit, settings.admin), prefix=admin_path, include_in_schema=False)
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

    app.router.lifespan_context = lifespan  # pyright: ignore[reportAttributeAccessIssue]  # Starlette allows this
    app.state.agentifyapi = gw
    return gw

"""The MCP gateway.

One low-level MCP server, served over streamable HTTP, answers on two kinds of paths:

* ``/mcp`` - meta-tools for incremental discovery (discover_servers, list_tools,
  get_tool_schema, invoke_tool). Context stays small no matter how many tools exist.
* ``/servers/{name}/mcp`` - every enabled tool of one service exposed directly, for
  clients that prefer classic tool lists.

Only approved + enabled tool versions are ever visible, and discovery only lists the tools the
caller's policy allows it to invoke. Every invocation goes through
policy -> HTTP forward -> projection -> PII redaction -> audit.
"""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any, cast
from urllib.parse import quote

import httpx
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.requests import Request
from starlette.routing import Route

from .config import Settings
from .governance import AuditLog, Caller, is_allowed, project, redact, resolve_caller
from .registry import Registry

META_TOOLS = [
    types.Tool(
        name="discover_servers",
        description=(
            "Find internal services (virtual MCP servers) relevant to a task. Start here. "
            "Returns server names, owners and how many tools each has."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text keywords, e.g. 'refund order'. Empty lists all."}
            },
        },
    ),
    types.Tool(
        name="list_tools",
        description=("List the enabled tools of one server with one-line descriptions (no schemas)."),
        inputSchema={
            "type": "object",
            "properties": {"server": {"type": "string"}, "query": {"type": "string"}},
            "required": ["server"],
        },
    ),
    types.Tool(
        name="get_tool_schema",
        description=("Get the full input schema and description for one tool before calling it."),
        inputSchema={"type": "object", "properties": {"tool": {"type": "string"}}, "required": ["tool"]},
    ),
    types.Tool(
        name="invoke_tool",
        description=(
            "Call a tool. `args` must match its input schema (path/query params by name, JSON body "
            "under 'body'). Pass `fields` (dotted paths, e.g. ['id','items.sku']) to return only what you need."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "tool": {"type": "string"},
                "args": {"type": "object"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["tool"],
        },
    ),
]


class ToolError(Exception):
    pass


def _score(text: str, query: str) -> int:
    words = [w for w in query.lower().split() if w]
    text = text.lower()
    return sum(text.count(w) for w in words)


class Gateway:
    def __init__(self, registry: Registry, settings: Settings, audit: AuditLog | None = None):
        self.registry = registry
        self.settings = settings
        self.audit = audit or AuditLog(settings.audit_log)
        self.transports: dict[str, httpx.AsyncBaseTransport] = {}  # server -> in-process ASGI transport
        self.server = Server("agentifyapi")
        self._register_handlers()
        self.manager = StreamableHTTPSessionManager(app=self.server, stateless=True, json_response=True)

    # ------------------------------------------------------------ discovery
    # `caller` filters results to what the policy lets that caller invoke (MCP requests always pass
    # one). None means no policy filter, for in-process use by the owner.
    def _visible(self, tool: str, caller: Caller | None) -> bool:
        return caller is None or is_allowed(self.settings.policy, caller, tool)

    def _live_tools(self, server: str, caller: Caller | None) -> list[dict]:
        out = []
        for t in self.registry.tools(server, enabled_only=True):
            d = self.registry.live_definition(t["name"])
            if d and self._visible(d["name"], caller):
                out.append(d)
        return out

    def discover_servers(self, query: str = "", caller: Caller | None = None) -> list[dict]:
        out = []
        for s in self.registry.servers():
            tools = self._live_tools(s["name"], caller)
            if not tools:
                continue
            blob = s["name"] + " " + " ".join(d["name"] + " " + d.get("description", "") for d in tools)
            score = _score(blob, query) if query else 1
            if score:
                out.append({"server": s["name"], "owner": s["owner"], "tools": len(tools), "_score": score})
        out.sort(key=lambda x: -x["_score"])
        return [{k: v for k, v in o.items() if k != "_score"} for o in out]

    def list_tools(self, server: str, query: str = "", caller: Caller | None = None) -> list[dict]:
        return [
            {"tool": d["name"], "method": d["method"], "description": d.get("description", "")}
            for d in self._live_tools(server, caller)
            if not query or _score(d["name"] + " " + d.get("description", ""), query)
        ]

    def get_tool_schema(self, tool: str, caller: Caller | None = None) -> dict:
        d = self.registry.live_definition(tool)
        if not d or not self._visible(tool, caller):
            raise ToolError(f"tool {tool!r} is not available (unknown, not approved, or disabled)")
        return {
            "tool": d["name"],
            "description": d.get("description", ""),
            "input_schema": d["input_schema"],
            "output_schema": d.get("output_schema"),
            "side_effects": d["method"] != "GET",
        }

    # ------------------------------------------------------------ invocation
    async def invoke(self, tool: str, args: dict | None, fields: list[str] | None, api_key: str | None) -> Any:
        args = dict(args or {})
        caller = resolve_caller(self.settings.policy, api_key)
        started = time.time()
        event: dict[str, Any] = {
            "event": "invoke",
            "tool": tool,
            "caller": caller.name,
            "arg_keys": sorted(args),
            "fields": fields,
        }
        try:
            d = self.registry.live_definition(tool)
            if not d:
                raise ToolError(f"tool {tool!r} is not available (unknown, not approved, or disabled)")
            if not is_allowed(self.settings.policy, caller, tool):
                event["decision"] = "denied"
                raise ToolError(f"caller {caller.name!r} is not permitted to call {tool!r}")
            event["decision"] = "allowed"
            missing = [r for r in d["input_schema"].get("required", []) if r not in args]
            if missing:
                raise ToolError(f"missing required arguments: {missing}")
            path = d["path"]
            for p in d["path_params"]:
                path = path.replace("{" + p + "}", quote(str(args[p]), safe=""))
            params = {q: args[q] for q in d["query_params"] if q in args and args[q] is not None}
            headers = {h: str(args[h]) for h in d["header_params"] if h in args}
            headers["x-agentifyapi-caller"] = caller.name
            body = args.get("body") if d["has_body"] else None
            resp = await self._send(d["server"], d["method"], path, params, headers, body)
            event["status"] = resp.status_code
            try:
                data: Any = resp.json()
            except ValueError:
                data = resp.text
            if resp.status_code >= 400:
                raise ToolError(f"upstream returned {resp.status_code}: {json.dumps(data)[:500]}")
            data = project(data, fields)
            if self.settings.redact_pii:
                data, n = redact(data)
                event["redactions"] = n
            return data
        except ToolError as exc:
            event["error"] = str(exc)
            raise
        finally:
            event["ms"] = round((time.time() - started) * 1000, 1)
            self.audit.write(**event)

    async def _send(self, server: str, method: str, path: str, params, headers, body) -> httpx.Response:
        transport = self.transports.get(server)
        if transport is not None:
            base = "http://embedded"
        else:
            srv = self.registry.server(server)
            if not srv or not srv["base_url"]:
                raise ToolError(f"server {server!r} has no base_url configured")
            base = srv["base_url"]
        async with httpx.AsyncClient(base_url=base, transport=transport, timeout=30) as client:
            return await client.request(
                method, path, params=params, headers=headers, json=body if body is not None else None
            )

    # ------------------------------------------------------------ MCP wiring
    def _request_info(self) -> tuple[str, str | None]:
        req = cast(Request | None, self.server.request_context.request)
        path = req.url.path if req is not None else "/mcp"
        key = None
        if req is not None:
            key = req.headers.get("x-api-key")
            auth = req.headers.get("authorization", "")
            if not key and auth.lower().startswith("bearer "):
                key = auth[7:]
        return path, key

    @staticmethod
    def _server_from_path(path: str) -> str | None:
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[-3] == "servers" and parts[-1] == "mcp":
            return parts[-2]
        return None

    def _register_handlers(self) -> None:
        srv = self.server

        @srv.list_tools()
        async def _list_tools() -> list[types.Tool]:
            path, key = self._request_info()
            server = self._server_from_path(path)
            if server is None:
                return META_TOOLS
            caller = resolve_caller(self.settings.policy, key)
            out = []
            for d in self._live_tools(server, caller):
                schema = json.loads(json.dumps(d["input_schema"]))
                schema.setdefault("properties", {})["_fields"] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional response projection (dotted paths).",
                }
                out.append(
                    types.Tool(
                        name=d["name"].split(".", 1)[1], description=d.get("description", ""), inputSchema=schema
                    )
                )
            return out

        @srv.call_tool()
        async def _call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            path, key = self._request_info()
            server = self._server_from_path(path)
            caller = resolve_caller(self.settings.policy, key)
            try:
                if server is not None:
                    args = dict(arguments or {})
                    fields = args.pop("_fields", None)
                    result = await self.invoke(f"{server}.{name}", args, fields, key)
                elif name == "discover_servers":
                    result = self.discover_servers(arguments.get("query", ""), caller)
                elif name == "list_tools":
                    result = self.list_tools(arguments["server"], arguments.get("query", ""), caller)
                elif name == "get_tool_schema":
                    result = self.get_tool_schema(arguments["tool"], caller)
                elif name == "invoke_tool":
                    result = await self.invoke(arguments["tool"], arguments.get("args"), arguments.get("fields"), key)
                else:
                    raise ToolError(f"unknown tool {name!r}")
            except ToolError as exc:
                raise ValueError(str(exc)) from exc  # surfaces as isError=true to the client
            return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    async def asgi(self, scope, receive, send) -> None:
        await self.manager.handle_request(scope, receive, send)

    def routes(self, prefix: str = "") -> list[Route]:
        app = _ASGIEndpoint(self)  # a plain ASGI callable (not a function) so Starlette passes it raw
        return [Route(f"{prefix}/mcp", endpoint=app), Route(f"{prefix}/servers/{{name}}/mcp", endpoint=app)]

    @contextlib.asynccontextmanager
    async def lifespan(self):
        async with self.manager.run():
            yield


class _ASGIEndpoint:
    def __init__(self, gw: Gateway):
        self.gw = gw

    async def __call__(self, scope, receive, send):
        await self.gw.manager.handle_request(scope, receive, send)

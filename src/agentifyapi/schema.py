"""OpenAPI operation -> MCP tool definition translation.

A tool definition is a plain dict (stored as JSON in the registry):
  {name, server, method, path, path_params, query_params, header_params,
   has_body, input_schema, output_schema, summary, description, tags, dependencies}
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def resolve_refs(node: Any, spec: dict, _seen: tuple = ()) -> Any:
    """Inline local $ref pointers (#/components/...). Cycles are cut with a stub."""
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/"):
            ref = node["$ref"]
            if ref in _seen:
                return {"type": "object", "description": f"(recursive {ref.split('/')[-1]})"}
            target: Any = spec
            for part in ref[2:].split("/"):
                target = target.get(part, {})
            merged = {**copy.deepcopy(target), **{k: v for k, v in node.items() if k != "$ref"}}
            return resolve_refs(merged, spec, _seen + (ref,))
        return {k: resolve_refs(v, spec, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_refs(v, spec, _seen) for v in node]
    return node


def tool_slug(operation: dict, method: str, path: str) -> str:
    """Friendly tool name. FastAPI operationIds look like `get_order_orders__order_id__get`;
    strip the generated `<path>_<method>` suffix to recover the route function name."""
    op_id = operation.get("operationId")
    if op_id:
        suffix = re.sub(r"\W", "_", path) + "_" + method
        if op_id.endswith(suffix) and len(op_id) > len(suffix):
            op_id = op_id[: -len(suffix)]
        return re.sub(r"[^a-zA-Z0-9_]", "_", op_id).strip("_")
    return re.sub(r"[^a-zA-Z0-9]+", "_", f"{method}_{path}").strip("_").lower()


def operation_to_tool(
    server: str, method: str, path: str, operation: dict, spec: dict, name: str | None = None
) -> dict:
    op = resolve_refs(operation, spec)
    props: dict[str, Any] = {}
    required: list[str] = []
    groups: dict[str, list[str]] = {"path": [], "query": [], "header": []}
    for p in op.get("parameters", []):
        loc = p.get("in")
        if loc not in groups:
            continue
        groups[loc].append(p["name"])
        schema = dict(p.get("schema", {}))
        schema.pop("title", None)
        if p.get("description"):
            schema["description"] = p["description"]
        props[p["name"]] = schema
        if p.get("required") or loc == "path":
            required.append(p["name"])
    has_body = False
    body = op.get("requestBody")
    if body:
        content = body.get("content", {})
        media = content.get("application/json") or next(iter(content.values()), {})
        if "schema" in media:
            has_body = True
            props["body"] = media["schema"]
            if body.get("required"):
                required.append("body")
    output_schema = None
    for code in ("200", "201", "202"):
        resp = op.get("responses", {}).get(code)
        if resp:
            output_schema = resp.get("content", {}).get("application/json", {}).get("schema")
            break
    input_schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        input_schema["required"] = required
    return {
        "name": f"{server}.{name or tool_slug(op, method, path)}",
        "server": server,
        "method": method.upper(),
        "path": path,
        "path_params": groups["path"],
        "query_params": groups["query"],
        "header_params": groups["header"],
        "has_body": has_body,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "summary": op.get("summary", ""),
        "doc": op.get("description", ""),
        "tags": op.get("tags", []),
        "dependencies": op.get("x-agentifyapi-dependencies", []),
        "deprecated": bool(op.get("deprecated")),
    }


def spec_to_tools(server: str, spec: dict, names: dict[tuple[str, str], str] | None = None) -> list[dict]:
    tools = []
    for path, item in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            if method in item:
                op = item[method]
                if op.get("x-agentifyapi-exclude"):
                    continue
                tools.append(
                    operation_to_tool(server, method, path, op, spec, (names or {}).get((method.upper(), path)))
                )
    return tools


def definition_hash(tool: dict) -> str:
    """Hash of the *contract* only (not the generated description), so a
    non-deterministic LLM description never creates a spurious revision."""
    contract = {
        k: tool.get(k)
        for k in (
            "method",
            "path",
            "input_schema",
            "output_schema",
            "path_params",
            "query_params",
            "header_params",
            "doc",
            "summary",
        )
    }
    return hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:16]

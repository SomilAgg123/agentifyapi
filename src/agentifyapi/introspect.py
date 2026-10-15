"""FastAPI-native introspection.

Rather than only reading /openapi.json, we import the app object and walk its routes so we
can recover things OpenAPI loses: the route function name (clean tool names), the full
docstring, and the dependency graph (e.g. `Depends(require_admin)`), which owners see during
review. Pydantic models still flow through FastAPI's own app.openapi() so schemas are exact.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any


def import_app(target: str, app_dir: str | None = None):
    module_name, _, attr = target.partition(":")
    attr = attr or "app"
    if app_dir and app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    module = importlib.import_module(module_name)
    obj = module
    for part in attr.split("."):
        obj = getattr(obj, part)
    if callable(obj) and not hasattr(obj, "routes"):  # app factory
        obj = obj()
    return obj


def _dependency_names(dependant) -> list[str]:
    names = []
    for dep in getattr(dependant, "dependencies", []) or []:
        call = getattr(dep, "call", None)
        if call is not None:
            names.append(getattr(call, "__name__", repr(call)))
        names.extend(_dependency_names(dep))
    return sorted(set(names))


def introspect_app(app) -> tuple[dict, dict[tuple[str, str], str]]:
    """Return (enriched OpenAPI spec, {(METHOD, path): route_function_name})."""
    from fastapi.routing import APIRoute

    spec: dict[str, Any] = app.openapi()
    names: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        doc = inspect.getdoc(route.endpoint) or ""
        deps = _dependency_names(route.dependant)
        for method in route.methods or []:
            names[(method, route.path_format)] = route.name
            op = spec.get("paths", {}).get(route.path_format, {}).get(method.lower())
            if op is None:
                continue
            if doc and not op.get("description"):
                op["description"] = doc
            if deps:
                op["x-agentifyapi-dependencies"] = deps
            if (route.openapi_extra or {}).get("x-agentifyapi-exclude"):
                op["x-agentifyapi-exclude"] = True
    return spec, names

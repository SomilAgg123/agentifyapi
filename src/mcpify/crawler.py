"""Crawler: fetch specs (FastAPI import or HTTP), translate, propose revisions."""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import ServiceConfig, Settings
from .describe import describe
from .introspect import import_app, introspect_app
from .registry import Registry
from .schema import definition_hash, spec_to_tools

log = logging.getLogger("mcpify.crawler")


def fetch_spec(svc: ServiceConfig, app=None) -> tuple[dict, dict, str]:
    """Returns (spec, route_names, source)."""
    if app is not None:
        spec, names = introspect_app(app)
        return spec, names, "fastapi:embedded"
    if svc.app:
        try:
            spec, names = introspect_app(import_app(svc.app, svc.app_dir))
            return spec, names, f"fastapi:{svc.app}"
        except Exception as exc:  # fall back to HTTP if we can't import (missing deps etc.)
            if not (svc.openapi_url or svc.base_url):
                raise
            log.warning("import of %s failed (%s); falling back to HTTP", svc.app, exc)
    if svc.proto:
        raise NotImplementedError("Protobuf/gRPC crawling is a roadmap item; see docs/DESIGN.md")
    url = svc.openapi_url or (svc.base_url or "").rstrip("/")
    if not url.endswith(".json"):
        url += "/openapi.json"
    r = httpx.get(url, timeout=15)
    r.raise_for_status()
    return r.json(), {}, f"openapi:{url}"


def crawl_service(reg: Registry, svc: ServiceConfig, app=None) -> dict[str, list[str]]:
    spec, names, source = fetch_spec(svc, app)
    reg.upsert_server(svc.name, svc.owner, svc.base_url, source)
    report: dict[str, list[str]] = {"new": [], "changed": [], "unchanged": [], "removed": []}
    seen = set()
    for tool in spec_to_tools(svc.name, spec, names):
        seen.add(tool["name"])
        h = definition_hash(tool)
        if reg.latest_hash(tool["name"]) != h:  # only pay for an LLM description on real changes
            tool["description"] = describe(tool)
        report[reg.propose(tool, h)].append(tool["name"])
    report["removed"] = reg.mark_removed(svc.name, seen)
    return report


def crawl_all(reg: Registry, settings: Settings, only: str | None = None) -> dict[str, dict]:
    out = {}
    for svc in settings.services:
        if only and svc.name != only:
            continue
        try:
            out[svc.name] = crawl_service(reg, svc)
        except Exception as exc:
            log.error("crawl of %s failed: %s", svc.name, exc)
            out[svc.name] = {"error": [str(exc)]}
    return out


async def crawl_forever(reg: Registry, settings: Settings) -> None:
    while settings.crawl_interval_seconds > 0:
        await asyncio.to_thread(crawl_all, reg, settings)
        await asyncio.sleep(settings.crawl_interval_seconds)

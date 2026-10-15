"""Command line: crawl, review, approve, serve."""

from __future__ import annotations

import argparse
import json
import sys

from .admin import revision_diff
from .config import ServiceConfig, load_settings
from .crawler import crawl_all, crawl_service
from .registry import Registry, RegistryError

PROG = "agentifyapi"


def _registry(args) -> Registry:
    settings = load_settings(args.config)
    return Registry(args.db or settings.database)


def cmd_crawl(args) -> int:
    settings = load_settings(args.config)
    reg = Registry(args.db or settings.database)
    if args.app or args.url:
        name = args.name or (args.app.split(":")[0].split(".")[0] if args.app else "service")
        svc = ServiceConfig(
            name=name, owner=args.owner, app=args.app, app_dir=args.app_dir, base_url=args.base_url or args.url
        )
        report = {name: crawl_service(reg, svc)}
    else:
        report = crawl_all(reg, settings, args.service)
    for server, r in report.items():
        print(f"{server}: " + ", ".join(f"{k}={len(v)}" for k, v in r.items()))
        for k in ("new", "changed", "removed", "error"):
            for t in r.get(k, []):
                print(f"  {k:8} {t}")
    if any(r.get("new") or r.get("changed") for r in report.values()):
        print(f"\nReview with `{PROG} tools diff <tool>` then `{PROG} tools approve <tool>`.")
    return 1 if any("error" in r for r in report.values()) else 0


def cmd_tools(args) -> int:
    reg = _registry(args)
    try:
        if args.action == "list":
            rows = reg.tools(args.target)
            if args.json:
                print(json.dumps(rows, indent=2))
                return 0
            print(f"{'TOOL':40} {'LIVE':5} {'STATE':9} PENDING")
            for t in rows:
                print(
                    f"{t['name']:40} {('v' + str(t['current_version'])) if t['current_version'] else '-':5} "
                    f"{'enabled' if t['enabled'] else 'disabled':9} {t['pending'] or ''}"
                )
            return 0
        if not args.target:
            print("tool name required", file=sys.stderr)
            return 2
        targets = [t["name"] for t in reg.tools(args.target[:-2])] if args.target.endswith(".*") else [args.target]
        for tool in targets:
            if args.action == "diff":
                print(revision_diff(reg, tool) or f"{tool}: no changes")
            elif args.action == "approve":
                print(f"{tool}: approved v{reg.approve(tool, by=args.by)}")
            elif args.action == "reject":
                reg.reject(tool, by=args.by)
                print(f"{tool}: pending revision rejected")
            elif args.action in ("enable", "disable"):
                reg.set_enabled(tool, args.action == "enable")
                print(f"{tool}: {args.action}d")
            elif args.action == "rollback":
                print(f"{tool}: rolled back to v{reg.rollback(tool)}")
            elif args.action == "history":
                for r in reg.revisions(tool):
                    print(f"v{r['version']} {r['status']:10} {r['spec_hash']} {r['decided_by'] or ''}")
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .app import create_app

    settings = load_settings(args.config)
    if args.db:
        settings.database = args.db
    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=PROG, description="Owner-approved MCP tools for FastAPI services.")
    p.add_argument("-c", "--config", help="YAML config (services, policy)")
    p.add_argument("--db", help="registry SQLite path (overrides config)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crawl", help="crawl configured services, or one FastAPI app / URL")
    c.add_argument("--app", help="import path of a FastAPI app, e.g. myservice.main:app")
    c.add_argument("--app-dir", help="repo directory to import from (added to sys.path)")
    c.add_argument("--url", help="OpenAPI URL or service base URL (HTTP fallback)")
    c.add_argument("--base-url", help="where the gateway should send calls for this service")
    c.add_argument("--name", help="server name (default: module name)")
    c.add_argument("--owner", help="owning team / person")
    c.add_argument("--service", help="only crawl this configured service")
    c.set_defaults(func=cmd_crawl)

    t = sub.add_parser("tools", help="list / review / approve tools")
    t.add_argument("action", choices=["list", "diff", "approve", "reject", "enable", "disable", "rollback", "history"])
    t.add_argument("target", nargs="?", help="tool name (or server.* ; or server for list)")
    t.add_argument("--by", default="cli", help="reviewer name recorded on the revision")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_tools)

    s = sub.add_parser("serve", help="run the gateway (+ admin UI at /admin)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    if getattr(args, "url", None) and not args.url.endswith(".json") and not args.base_url:
        args.base_url = args.url
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

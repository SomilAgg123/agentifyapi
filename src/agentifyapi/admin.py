"""Minimal admin UI (server-rendered HTML, no JS build) for reviewing revisions."""

from __future__ import annotations

import base64
import difflib
import html
import ipaddress
import json
import os
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .config import AdminConfig
from .registry import Registry, RegistryError

ADMIN_PASSWORD_ENV = "AGENTIFYAPI_ADMIN_PASSWORD"
ADMIN_USERNAME_ENV = "AGENTIFYAPI_ADMIN_USERNAME"

CSS = """body{font:14px system-ui;margin:2rem;max-width:1100px;color:#1d2433}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #e3e6ec;padding:6px;text-align:left}
.on{color:#0a7d32;font-weight:600}.off{color:#888}.pend{background:#fff4d6;padding:2px 6px;border-radius:4px}
pre{background:#f6f8fa;padding:10px;overflow:auto}.add{color:#0a7d32}.del{color:#b3261e}
button{margin-right:4px}form{display:inline}"""


def diff_text(old: dict | None, new: dict) -> str:
    a = json.dumps(old, indent=2, sort_keys=True).splitlines() if old else []
    b = json.dumps(new, indent=2, sort_keys=True).splitlines()
    return "\n".join(difflib.unified_diff(a, b, "live", "proposed", lineterm=""))


def revision_diff(reg: Registry, tool: str, version: int | None = None) -> str:
    revs = reg.revisions(tool)
    row = next((t for t in reg.tools() if t["name"] == tool), None)
    if not revs or row is None:
        raise RegistryError(f"unknown tool {tool!r}")
    pending = [r for r in revs if r["status"] == "pending" and (version is None or r["version"] == version)]
    target = pending[-1] if pending else revs[-1]
    live = next((r["definition"] for r in revs if r["version"] == row["current_version"]), None)
    return diff_text(live, target["definition"])


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><title>agentifyapi admin</title><style>{CSS}</style>"
        f"<h1>agentifyapi &middot; tool registry</h1>{body}"
    )


def _is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def admin_guard(cfg: AdminConfig | None = None):
    """FastAPI dependency enforcing `AdminConfig` (env vars override the config's credentials)."""
    cfg = cfg or AdminConfig()
    password = os.getenv(ADMIN_PASSWORD_ENV) or cfg.password
    username = os.getenv(ADMIN_USERNAME_ENV) or cfg.username

    def guard(request: Request) -> None:
        if password:
            auth = request.headers.get("authorization", "")
            scheme, _, value = auth.partition(" ")
            ok = False
            if scheme.lower() == "basic" and value:
                try:
                    user, _, pw = base64.b64decode(value).decode().partition(":")
                except (ValueError, UnicodeDecodeError):
                    user, pw = "", ""
                ok = secrets.compare_digest(user.encode(), username.encode()) & secrets.compare_digest(
                    pw.encode(), password.encode()
                )
            if not ok:
                raise HTTPException(
                    401, "admin authentication required", headers={"WWW-Authenticate": 'Basic realm="agentifyapi"'}
                )
            return
        if cfg.insecure_allow_remote:
            return
        if not _is_loopback(request.client.host if request.client else None):
            raise HTTPException(
                403,
                f"admin UI is restricted to localhost; set {ADMIN_PASSWORD_ENV} (or admin.password) to allow remote access",
            )

    return guard


def admin_router(reg: Registry, audit=None, admin: AdminConfig | None = None) -> APIRouter:
    r = APIRouter(dependencies=[Depends(admin_guard(admin))])

    @r.get("/", response_class=HTMLResponse)
    def index():
        rows = []
        owners = {s["name"]: s["owner"] or "-" for s in reg.servers()}
        for t in reg.tools():
            n = html.escape(t["name"])
            state = '<span class="on">enabled</span>' if t["enabled"] else '<span class="off">disabled</span>'
            pend = f'<span class="pend">{t["pending"]} pending</span>' if t["pending"] else ""
            rows.append(
                f'<tr><td><a href="tools/{n}">{n}</a></td><td>{html.escape(owners.get(t["server"], "-"))}'
                f"</td><td>v{t['current_version'] or '-'}</td><td>{state}</td><td>{pend}</td></tr>"
            )
        audit_html = ""
        if audit is not None and audit.records:
            audit_html = (
                "<h2>Recent calls</h2><pre>"
                + html.escape("\n".join(json.dumps(e) for e in audit.records[-20:]))
                + "</pre>"
            )
        return _page(
            "<table><tr><th>Tool</th><th>Owner</th><th>Live</th><th>State</th><th></th></tr>"
            + "".join(rows)
            + "</table>"
            + audit_html
        )

    @r.get("/tools/{tool}", response_class=HTMLResponse)
    def tool_page(tool: str):
        try:
            diff = revision_diff(reg, tool)
        except RegistryError as e:
            raise HTTPException(404, str(e)) from e
        row = next(t for t in reg.tools() if t["name"] == tool)
        revs = reg.revisions(tool)
        hist = "".join(
            f"<tr><td>v{x['version']}</td><td>{x['status']}</td><td>{x['spec_hash']}</td>"
            f"<td>{html.escape(x['decided_by'] or '')}</td></tr>"
            for x in revs
        )
        diff_html = "\n".join(
            f'<span class="{"add" if line.startswith("+") else "del" if line.startswith("-") else ""}">{html.escape(line)}</span>'
            for line in diff.splitlines()
        )
        t = html.escape(tool)

        def btn(action, label):
            return f'<form method="post" action="{t}/{action}"><button>{label}</button></form>'

        actions = (
            btn("approve", "Approve pending")
            + btn("reject", "Reject pending")
            + (btn("disable", "Disable") if row["enabled"] else btn("enable", "Enable"))
            + btn("rollback", "Rollback")
        )
        return _page(
            f'<p><a href="../">&larr; all tools</a></p><h2>{t}</h2>{actions}'
            f"<h3>Diff (live &rarr; latest proposed)</h3><pre>{diff_html or '(no changes)'}</pre>"
            f"<h3>History</h3><table><tr><th>Version</th><th>Status</th><th>Hash</th><th>By</th></tr>{hist}</table>"
        )

    @r.post("/tools/{tool}/{action}")
    def act(tool: str, action: str, by: str = Form("admin-ui")):
        try:
            {
                "approve": lambda: reg.approve(tool, by),
                "reject": lambda: reg.reject(tool, by),
                "enable": lambda: reg.set_enabled(tool, True),
                "disable": lambda: reg.set_enabled(tool, False),
                "rollback": lambda: reg.rollback(tool),
            }[action]()
        except KeyError:
            raise HTTPException(404, "unknown action") from None
        except RegistryError as e:
            raise HTTPException(400, str(e)) from e
        return RedirectResponse(f"../{tool}", status_code=303)

    return r

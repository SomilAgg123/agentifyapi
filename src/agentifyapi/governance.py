"""Runtime governance: caller policy, PII redaction, response projection, audit log."""

from __future__ import annotations

import fnmatch
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import PolicyConfig


# ---------------------------------------------------------------- policy
@dataclass
class Caller:
    name: str
    roles: list[str] = field(default_factory=list)
    authenticated: bool = True


ANONYMOUS = Caller("anonymous", [], authenticated=False)


def resolve_caller(policy: PolicyConfig, api_key: str | None) -> Caller:
    if api_key and api_key in policy.api_keys:
        c = policy.api_keys[api_key]
        return Caller(c.name, list(c.roles))
    return ANONYMOUS


def is_allowed(policy: PolicyConfig, caller: Caller, tool: str) -> bool:
    if not caller.authenticated:
        return policy.allow_anonymous
    for rule in policy.rules:
        if not any(fnmatch.fnmatchcase(tool, pat) for pat in rule.tools):
            continue
        if caller.name in rule.callers or set(caller.roles) & set(rule.roles) or "*" in rule.roles:
            return True
    return False


# ---------------------------------------------------------------- redaction
PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"),
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def redact_text(text: str) -> tuple[str, int]:
    count = 0

    def sub(kind):
        def _r(m):
            nonlocal count
            if kind == "card" and not _luhn(re.sub(r"\D", "", m.group())):
                return m.group()
            count += 1
            return f"[REDACTED:{kind}]"

        return _r

    for kind in ("email", "ssn", "card", "phone"):  # order matters: cards before phones
        text = PII_PATTERNS[kind].sub(sub(kind), text)
    return text, count


def redact(value: Any) -> tuple[Any, int]:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        n = 0
        out = {}
        for k, v in value.items():
            out[k], c = redact(v)
            n += c
        return out, n
    if isinstance(value, list):
        n = 0
        out_l = []
        for v in value:
            r, c = redact(v)
            out_l.append(r)
            n += c
        return out_l, n
    if isinstance(value, int) and not isinstance(value, bool) and len(str(abs(value))) >= 13:
        r, c = redact_text(str(value))
        return (r if c else value), c
    return value, 0


# ---------------------------------------------------------------- projection
def project(value: Any, fields: list[str] | None) -> Any:
    """Keep only the requested dotted paths, e.g. ["id", "items.sku", "customer.name"].
    Lists are mapped transparently, so "items.sku" works on a list of items."""
    if not fields:
        return value
    tree: dict = {}
    for f in fields:
        node = tree
        for part in f.split("."):
            node = node.setdefault(part, {})
    return _project(value, tree)


def _project(value: Any, tree: dict) -> Any:
    if not tree:
        return value
    if isinstance(value, list):
        return [_project(v, tree) for v in value]
    if isinstance(value, dict):
        return {k: _project(value[k], sub) for k, sub in tree.items() if k in value}
    return value


# ---------------------------------------------------------------- audit
class AuditLog:
    """Append-only JSON-lines audit log."""

    def __init__(self, path: str | None):
        self.path = path
        self._lock = threading.Lock()
        self.records: list[dict] = []  # in-memory tail for the admin UI / tests

    def write(self, **event: Any) -> None:
        event = {"ts": time.time(), **event}
        with self._lock:
            self.records = (self.records + [event])[-500:]
            if self.path:
                with open(self.path, "a") as fh:
                    fh.write(json.dumps(event, default=str) + "\n")

"""SQLite registry: servers, tools, and versioned revisions with an approval workflow.

Lifecycle: crawler proposes a revision (status=pending). Owner approves -> it becomes the
tool's current version. Tools are disabled by default; enabling is a separate, explicit step.
A spec change on an existing tool creates a new *pending* revision; the live version is
untouched until approved. Rollback re-points current_version to the previous approved one.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
  name TEXT PRIMARY KEY, owner TEXT, base_url TEXT, source TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS tools (
  name TEXT PRIMARY KEY, server TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
  current_version INTEGER, removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tool TEXT NOT NULL, version INTEGER NOT NULL,
  spec_hash TEXT NOT NULL, definition TEXT NOT NULL, status TEXT NOT NULL,
  created_at REAL, decided_by TEXT, decided_at REAL, UNIQUE(tool, version));
"""


class RegistryError(Exception):
    pass


class Registry:
    def __init__(self, path: str = "registry.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- servers
    def upsert_server(self, name: str, owner: str | None, base_url: str | None, source: str) -> None:
        self.db.execute(
            "INSERT INTO servers(name, owner, base_url, source, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET owner=excluded.owner, base_url=excluded.base_url, "
            "source=excluded.source, updated_at=excluded.updated_at",
            (name, owner, base_url, source, time.time()),
        )
        self.db.commit()

    def servers(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM servers ORDER BY name")]

    def server(self, name: str) -> dict | None:
        r = self.db.execute("SELECT * FROM servers WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None

    # ---- revisions
    def propose(self, definition: dict, spec_hash: str) -> str:
        """Record a crawled definition. Returns 'new' | 'changed' | 'unchanged'."""
        name = definition["name"]
        latest = self.db.execute(
            "SELECT * FROM revisions WHERE tool=? ORDER BY version DESC LIMIT 1", (name,)
        ).fetchone()
        if latest and latest["spec_hash"] == spec_hash:
            self.db.execute("UPDATE tools SET removed=0 WHERE name=?", (name,))
            self.db.commit()
            return "unchanged"
        version = (latest["version"] + 1) if latest else 1
        if latest and latest["status"] == "pending":  # superseded before review
            self.db.execute("UPDATE revisions SET status='superseded' WHERE id=?", (latest["id"],))
        self.db.execute("INSERT OR IGNORE INTO tools(name, server) VALUES(?,?)", (name, definition["server"]))
        self.db.execute("UPDATE tools SET removed=0 WHERE name=?", (name,))
        self.db.execute(
            "INSERT INTO revisions(tool, version, spec_hash, definition, status, created_at) VALUES(?,?,?,?,?,?)",
            (name, version, spec_hash, json.dumps(definition), "pending", time.time()),
        )
        self.db.commit()
        return "changed" if latest else "new"

    def mark_removed(self, server: str, seen: set[str]) -> list[str]:
        gone = [
            r["name"]
            for r in self.db.execute("SELECT name FROM tools WHERE server=? AND removed=0", (server,))
            if r["name"] not in seen
        ]
        for n in gone:  # endpoint disappeared upstream: hide it, keep history
            self.db.execute("UPDATE tools SET removed=1, enabled=0 WHERE name=?", (n,))
        self.db.commit()
        return gone

    def latest_hash(self, tool: str) -> str | None:
        r = self.db.execute(
            "SELECT spec_hash FROM revisions WHERE tool=? ORDER BY version DESC LIMIT 1", (tool,)
        ).fetchone()
        return r["spec_hash"] if r else None

    def revisions(self, tool: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM revisions WHERE tool=? ORDER BY version", (tool,))
        return [{**dict(r), "definition": json.loads(r["definition"])} for r in rows]

    def pending(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM revisions WHERE status='pending' ORDER BY tool, version")
        return [{**dict(r), "definition": json.loads(r["definition"])} for r in rows]

    def _tool_row(self, name: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM tools WHERE name=?", (name,)).fetchone()
        if not row:
            raise RegistryError(f"unknown tool {name!r}")
        return row

    def approve(self, tool: str, by: str = "cli", version: int | None = None) -> int:
        self._tool_row(tool)
        q = "SELECT * FROM revisions WHERE tool=? AND status='pending'"
        args: list[Any] = [tool]
        if version is not None:
            q += " AND version=?"
            args.append(version)
        rev = self.db.execute(q + " ORDER BY version DESC LIMIT 1", args).fetchone()
        if not rev:
            raise RegistryError(f"no pending revision for {tool!r}")
        self.db.execute(
            "UPDATE revisions SET status='approved', decided_by=?, decided_at=? WHERE id=?",
            (by, time.time(), rev["id"]),
        )
        self.db.execute("UPDATE tools SET current_version=? WHERE name=?", (rev["version"], tool))
        self.db.commit()
        return rev["version"]

    def reject(self, tool: str, by: str = "cli") -> None:
        self.db.execute(
            "UPDATE revisions SET status='rejected', decided_by=?, decided_at=? WHERE tool=? AND status='pending'",
            (by, time.time(), tool),
        )
        self.db.commit()

    def set_enabled(self, tool: str, enabled: bool) -> None:
        row = self._tool_row(tool)
        if enabled and row["current_version"] is None:
            raise RegistryError(f"{tool!r} has no approved version; approve it first")
        self.db.execute("UPDATE tools SET enabled=? WHERE name=?", (int(enabled), tool))
        self.db.commit()

    def rollback(self, tool: str) -> int:
        row = self._tool_row(tool)
        prev = self.db.execute(
            "SELECT version FROM revisions WHERE tool=? AND status='approved' AND version<? "
            "ORDER BY version DESC LIMIT 1",
            (tool, row["current_version"] or 0),
        ).fetchone()
        if not prev:
            raise RegistryError(f"no earlier approved version of {tool!r}")
        self.db.execute("UPDATE tools SET current_version=? WHERE name=?", (prev["version"], tool))
        self.db.commit()
        return prev["version"]

    # ---- reads
    def tools(self, server: str | None = None, enabled_only: bool = False) -> list[dict]:
        q = (
            "SELECT t.*, (SELECT COUNT(*) FROM revisions r WHERE r.tool=t.name AND r.status='pending') AS pending "
            "FROM tools t WHERE removed=0"
        )
        args: list[Any] = []
        if server:
            q += " AND server=?"
            args.append(server)
        if enabled_only:
            q += " AND enabled=1 AND current_version IS NOT NULL"
        return [dict(r) for r in self.db.execute(q + " ORDER BY name", args)]

    def live_definition(self, tool: str) -> dict | None:
        """The approved, enabled definition the gateway may serve, or None."""
        row = self.db.execute("SELECT * FROM tools WHERE name=? AND enabled=1 AND removed=0", (tool,)).fetchone()
        if not row or row["current_version"] is None:
            return None
        rev = self.db.execute(
            "SELECT definition FROM revisions WHERE tool=? AND version=?", (tool, row["current_version"])
        ).fetchone()
        return json.loads(rev["definition"])

# Design decisions

## Goal
Make FastAPI services usable by agents (coding agents and production agents) without
hand-writing MCP servers, and without letting auto-generated tools reach agents unreviewed.
Modeled on Uber's MCP Gateway (https://www.uber.com/blog/designing-mcp-gateway/), scoped to
what one team can run locally.

## 1. FastAPI-native first, OpenAPI second
Most new internal APIs written alongside agentic coding are Python + FastAPI. Importing the app
gives more than `/openapi.json`: the route function name (readable tool names), full docstrings,
and the `Depends()` graph, which tells a reviewer that a route needs `require_admin`. We still
build schemas from `app.openapi()` so Pydantic → JSON Schema is exactly FastAPI's. Plain HTTP
OpenAPI is the fallback and covers non-FastAPI services.

## 2. Two shapes, one core
`mount(app)` (embedded, in-process ASGI dispatch) for one service and `mcpify serve` (standalone)
for many. Both use the same Registry and Gateway classes.

## 3. Discovery doesn't imply exposure
Crawling only ever creates *pending revisions*. A tool is served only if it has an approved
version **and** is enabled. Approval and enablement are separate so an owner can stage a version.
A changed contract creates a new pending revision while the old approved version keeps serving.
Rollback re-points to the previous approved version; history is never deleted. Endpoints that
disappear upstream are hidden and disabled.

## 4. Hash the contract, not the prose
The revision hash covers method, path, parameters, input/output schema, summary and docstring,
but not the generated description. Otherwise a non-deterministic LLM would create a revision on
every crawl. Descriptions are generated once per contract change.

## 5. Pluggable descriptions with a deterministic fallback
Anthropic or OpenAI via env var; otherwise a template from summary, docstring, args and side
effects. The project must work fully offline, and tests force the template.

## 6. Incremental discovery over a flat tool list
With hundreds of tools, a flat `tools/list` floods the context. `/mcp` exposes four meta-tools
(discover → list → schema → invoke). `/servers/{name}/mcp` offers the flat view per service for
clients that want it. Search is keyword scoring in v1; a semantic index is on the roadmap.

## 7. One low-level MCP server, path-routed
Instead of one FastMCP instance per service (which needs a session manager and lifespan for
each, and can't add servers at runtime), a single low-level `mcp.server.lowlevel.Server` inspects
the request path to decide whether it's serving meta-tools or a specific service's tools. It's
stateless streamable HTTP with JSON responses, so it scales horizontally and needs no sticky sessions.

## 8. Governance pipeline order
policy → forward → **project → redact** → audit. Projection runs before redaction so redaction
only scans what is returned. The audit log records argument *keys*, not values, to avoid copying PII.

## 9. Policy: default deny, API keys → caller + roles
Allow-list rules with fnmatch patterns on tool names. `allow_anonymous` exists only for local
development. OAuth / end-user identity passthrough is on the roadmap.

## 10. Redaction is regex + Luhn
Emails, SSNs, phone numbers, and card numbers (Luhn-checked to avoid destroying order IDs). It's
deliberately simple. Field-level rules from Pydantic metadata are a planned improvement.

## 11. SQLite registry
Zero setup and enough for a single gateway. The Registry class is the seam for Postgres.

## 12. MCP SDK pinned to 1.x
`mcp>=1.12,<2`. The 2.x line renames FastMCP and changes server APIs; we will migrate once it
settles. Only `lowlevel.Server`, `StreamableHTTPSessionManager` and the client are used, which
keeps the migration small.

## Extension points
- `crawler.fetch_spec`: add `proto:` (gRPC descriptor sets) here.
- `describe.describe`: add providers.
- `Gateway.discover_servers` / `list_tools`: swap in semantic search.
- `governance.PII_PATTERNS`, `is_allowed`: richer policy engines (OPA, Cedar).

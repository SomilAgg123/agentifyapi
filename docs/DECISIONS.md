# Decision log

Short, dated record of choices made while building v1. Longer rationale is in [DESIGN.md](DESIGN.md).

| Date | Decision | Why | Alternative rejected |
|---|---|---|---|
| 2026-10-15 | Python + FastAPI, MCP SDK pinned `>=1.12,<2` | Target users build on FastAPI. SDK 2.x renames FastMCP and changes server APIs. | Track 2.x now and churn on an unsettled API. |
| 2026-10-15 | FastAPI-native crawl (import `module:app`) is primary; `/openapi.json` is the fallback | Importing recovers route names, docstrings and the `Depends()` graph that OpenAPI drops. | OpenAPI-only, which gives worse tool names and no dependency info for reviewers. |
| 2026-10-15 | Embedded `mount(app)` and standalone `serve` share one Registry and Gateway | One code path to test. Embedded dispatches in-process via ASGI transport. | A separate embedded implementation. |
| 2026-10-15 | Tools are disabled by default; approve and enable are separate steps | "Discovery doesn't imply exposure" (Uber). Owners can stage a version before exposing it. | Auto-enable on approve. |
| 2026-10-15 | Revision hash covers the contract, not the generated description | LLM wording would otherwise create a pending revision on every crawl. Descriptions are only generated when the contract changes. | Hash the full definition. |
| 2026-10-15 | One low-level MCP `Server`, routed by request path (`/mcp` vs `/servers/{name}/mcp`) | One session manager and one lifespan. Services added at runtime need no restart. Stateless JSON mode needs no sticky sessions. | A FastMCP instance per service. |
| 2026-10-15 | Order: policy, forward, project, redact, audit. Audit stores argument keys only. | Redact only what is returned. Keep PII out of the audit log. | Redact before projecting. Log full arguments. |
| 2026-10-15 | Default-deny policy with API key mapped to caller and roles; `allow_anonymous` for dev only | Safe default without needing an identity provider in v1. | OAuth in v1 (on the roadmap). |
| 2026-10-15 | Card redaction requires a Luhn-valid number | Plain regex would destroy order IDs and other long numbers. | Regex only. |
| 2026-10-15 | `scripts/verify_demo.py` proves the real running demo with literal assertions | Unit tests alone don't prove the demo a user runs. It checks 8 behaviors over real MCP HTTP. | Eyeballing demo output. |
| 2026-10-15 | Project name isolated behind `scripts/rename.py` | Name is undecided (`agentifyapi` is taken on PyPI and GitHub). Tested: rename then pytest stays green. | Hand renaming later. |
| 2026-10-15 | Crawler only calls the describer when the contract hash changed | Removed a redundant second `propose` path. Unchanged crawls cost zero LLM calls. | Re-describe every crawl. |
| 2026-10-15 | Protobuf/gRPC is a typed config field (`proto:`) that raises `NotImplementedError` | The extension point is visible without shipping half a feature. | Omit it entirely. |

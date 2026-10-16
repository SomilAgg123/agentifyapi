# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) at 0.x.

## [Unreleased]

## [0.2.0] - 2026-10-16

### Changed

- **Behavior change:** the admin UI (`/admin`, `/mcp-admin`) now requires a password for remote
  access (#4). Same-machine (loopback) access works without one. Set `AGENTIFYAPI_ADMIN_PASSWORD`,
  `admin.password`, or `mount(app, admin_password=...)` to enable HTTP Basic auth for remote clients.
  `admin.insecure_allow_remote` / `admin_allow_remote=True` opens it without a password for development.

### Fixed

- Path parameters containing `/` (e.g. sku `A/1`) no longer 404 in embedded `mount()` mode (#5).
  Values are percent-encoded when forwarded. In standalone gateway mode, a standard FastAPI upstream
  must declare the route as `{sku:path}` to accept the encoded slash.
- README: install section now leads with `pip install agentifyapi` (git install only for the latest
  commit on main) (#9), and PyPI / Python badges are cache-busted so they show live data (#10).

## [0.1.0] - 2026-10-15

First release.

### Added

- FastAPI-native crawling: import an app (`agentifyapi crawl --app pkg.mod:app`) and turn routes,
  Pydantic models, docstrings, tags and `Depends()` into MCP tools, with `/openapi.json` as a fallback.
- `mount(app)`: add a governed `/mcp` endpoint and `/mcp-admin` review UI to an existing FastAPI app.
- A standalone gateway (`agentifyapi serve`) for many services, with discovery meta-tools and
  per-service endpoints.
- Owner approval with versioned revisions, diffs and rollback. Tools are disabled by default.
- Per-caller and per-role policies, response projection, PII redaction and a JSON-lines audit log.
- A demo with mock orders and users services, `scripts/verify_demo.py`, and an example MCP client.

[Unreleased]: https://github.com/SomilAgg123/agentifyapi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/SomilAgg123/agentifyapi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/SomilAgg123/agentifyapi/releases/tag/v0.1.0

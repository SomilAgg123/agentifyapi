# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) at 0.x.

## [Unreleased]

### Added

- Admin UI access control (#4). With no password the admin UI (`/admin`, `/mcp-admin`) only answers
  loopback clients; set `AGENTIFYAPI_ADMIN_PASSWORD`, `admin.password`, or
  `mount(app, admin_password=...)` to require HTTP Basic auth. `admin.insecure_allow_remote` /
  `admin_allow_remote=True` opens it without a password for development.
- README PyPI and Python-version badges use distinct shields.io URLs so GitHub fetches the live
  `agentifyapi` 0.1.0 images.
- README install section (`pip install agentifyapi`, plus the latest commit on main) and a three-column
  comparison with fastapi_mcp and FastMCP.
- README front-and-center example (`examples/quickstart.py`) with `scripts/verify_quickstart.py` in CI.
- Packaging metadata, `py.typed`, and versions computed from git tags (hatch-vcs).
- CI: ruff, pyright in standard mode, pytest with coverage on Python 3.11-3.13,
  a job that runs the demo verification, and a zizmor workflow audit.
- A release workflow that publishes to PyPI with trusted publishing when a GitHub release is published.
- Pre-commit hooks (ruff, pyproject validation, gitleaks), Dependabot, issue forms, and a PR template.

### Fixed

- Path parameters containing `/` (e.g. sku `A/1`) no longer 404 in embedded `mount()` mode (#5).
  Values are percent-encoded when forwarded, and in-process dispatch routes on the encoded segment.

### Changed

- The admin UI is no longer reachable from non-localhost clients unless a password is configured
  (or `insecure_allow_remote` is set).

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

[Unreleased]: https://github.com/SomilAgg123/agentifyapi/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SomilAgg123/agentifyapi/releases/tag/v0.1.0

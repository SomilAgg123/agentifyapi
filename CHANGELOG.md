# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html) at 0.x.

## [Unreleased]

### Added

- README install section (`pip install agentifyapi`, plus the latest commit on main) and a three-column
  comparison with fastapi_mcp and FastMCP.
- README front-and-center example (`examples/quickstart.py`) with `scripts/verify_quickstart.py` in CI.
- Packaging metadata, `py.typed`, and versions computed from git tags (hatch-vcs).
- CI: ruff, pyright in standard mode, pytest with coverage on Python 3.11-3.13,
  a job that runs the demo verification, and a zizmor workflow audit.
- A release workflow that publishes to PyPI with trusted publishing when a GitHub release is published.
- Pre-commit hooks (ruff, pyproject validation, gitleaks), Dependabot, issue forms, and a PR template.

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

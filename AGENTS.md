# Working on agentifyapi

For coding agents. Read `docs/DESIGN.md` before changing behaviour.

## Layout

- `src/agentifyapi/schema.py` turns an OpenAPI operation into a tool definition (a plain dict).
- `introspect.py` imports a FastAPI app and enriches that spec (names, docstrings, dependencies).
- `crawler.py` turns specs into pending revisions. `registry.py` stores versions in SQLite.
- `gateway.py` serves MCP over streamable HTTP. `governance.py` does policy, projection, redaction, audit.
- `embed.py` (`mount`) and `app.py` (`create_app`) are the two ways to run it.

## Rules

- A tool must never be reachable by an agent without an explicit approve and enable, except the
  opt-in `auto_approve` flag in `mount()`.
- The revision hash covers the contract only. Don't include the generated description in it.
- Keep the public surface small: `mount`, `create_app`, and the `agentifyapi` CLI.

## Verify

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest --cov
uv run python scripts/verify_demo.py   # boots the real demo and checks it
```

## Tests

Call the code the way a user does and assert exact values. End-to-end tests in `tests/test_e2e.py`
go over real MCP HTTP and carry the `integration` marker. Run them with `uv run pytest -m integration`.

## Versions

The version comes from git tags through hatch-vcs. Releases are `v0.x.y` tags plus a GitHub release,
which triggers `.github/workflows/publish.yml`. Add user-visible changes under `Unreleased` in
`CHANGELOG.md`.

# Contributing

Thanks for helping! The project is small on purpose, so please keep changes focused.
By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

```bash
uv sync                      # creates .venv from uv.lock (Python 3.11+)
uv run pre-commit install    # ruff, format, pyproject validation, gitleaks on every commit
```

## Before opening a PR

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest --cov          # coverage must stay at or above the fail_under in pyproject.toml
uv run python scripts/verify_demo.py
```

- New behaviour needs a test that calls the code as a user would and asserts exact values.
  Gateway behaviour should be covered over real MCP (`tests/test_e2e.py`, marker `integration`).
- Add user-visible changes under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).
- Record notable design choices in `docs/DECISIONS.md`.

Good first areas are labelled [good first issue](https://github.com/SomilAgg123/agentifyapi/labels/good%20first%20issue).

## Safety rule

Nothing may make a tool reachable without an explicit approve and enable, except the opt-in
`auto_approve` development flag.

## Releasing (maintainers)

1. Move `Unreleased` entries in CHANGELOG.md under a new version heading.
2. Tag `vX.Y.Z` on main and publish a GitHub release from it. The version comes from the tag.
3. `.github/workflows/publish.yml` builds and publishes to PyPI with trusted publishing.

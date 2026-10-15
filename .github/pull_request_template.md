## What and why

<!-- One or two sentences. Link the issue: Fixes #123 -->

## How I verified it

- [ ] `uv run pytest --cov` passes
- [ ] `uv run pyright` and `uv run ruff check .` are clean
- [ ] `uv run python scripts/verify_demo.py` passes (if gateway behaviour changed)
- [ ] CHANGELOG.md `Unreleased` updated (if user-visible)

## Safety

- [ ] Nothing makes a tool reachable without an explicit approve + enable

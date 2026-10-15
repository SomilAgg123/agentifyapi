# Contributing

Thanks for helping! The project is small on purpose, so please keep changes focused.

1. `pip install -e ".[dev]"` (Python 3.11+), then `pytest -q`. CI runs 3.11 to 3.13.
2. `make demo` should keep working end to end.
3. New behaviour needs a test. Gateway behaviour should be covered over real MCP (see `tests/test_e2e.py`).
4. Record notable design choices in `docs/DESIGN.md`.

Good first areas: Protobuf crawling (`crawler.fetch_spec`), a semantic discovery index
(`Gateway.discover_servers`), extra PII patterns (`governance.PII_PATTERNS`), admin UI polish.

Safety rule: nothing may make a tool reachable without an explicit approve + enable, except
the opt-in `auto_approve` dev flag.

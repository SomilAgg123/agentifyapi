import pytest

from agentifyapi.cli import main as cli
from agentifyapi.config import ServiceConfig
from agentifyapi.crawler import crawl_service
from agentifyapi.registry import Registry, RegistryError
from tests.test_schema import SPEC


def test_approval_flow_and_rollback(registry, monkeypatch):
    import copy

    spec = copy.deepcopy(SPEC)
    monkeypatch.setattr("agentifyapi.crawler.fetch_spec", lambda svc, app=None: (spec, {}, "fake"))
    svc = ServiceConfig(name="pets", owner="team-pets", base_url="http://x")
    r = crawl_service(registry, svc)
    assert sorted(r["new"]) == ["pets.get_pet", "pets.post_pets"]
    assert registry.live_definition("pets.get_pet") is None  # disabled by default
    with pytest.raises(RegistryError):
        registry.set_enabled("pets.get_pet", True)  # must approve first
    assert registry.approve("pets.get_pet", by="alice") == 1
    registry.set_enabled("pets.get_pet", True)
    assert registry.live_definition("pets.get_pet")["path"] == "/pets/{pet_id}"

    # re-crawl unchanged -> nothing pending
    assert crawl_service(registry, svc)["unchanged"]

    # spec change -> pending revision, live version untouched
    spec["paths"]["/pets/{pet_id}"]["get"]["parameters"].append(
        {"name": "fields", "in": "query", "schema": {"type": "string"}}
    )
    assert crawl_service(registry, svc)["changed"] == ["pets.get_pet"]
    assert "fields" not in registry.live_definition("pets.get_pet")["query_params"]
    assert registry.approve("pets.get_pet") == 2
    assert "fields" in registry.live_definition("pets.get_pet")["query_params"]
    assert registry.rollback("pets.get_pet") == 1
    assert "fields" not in registry.live_definition("pets.get_pet")["query_params"]

    # endpoint removed upstream -> hidden
    del spec["paths"]["/pets"]
    assert crawl_service(registry, svc)["removed"] == ["pets.post_pets"]


def test_cli(tmp_path, capsys):
    db = str(tmp_path / "c.db")
    assert (
        cli(
            [
                "--db",
                db,
                "crawl",
                "--app",
                "examples.services.orders:app",
                "--name",
                "orders",
                "--owner",
                "commerce",
                "--base-url",
                "http://x",
            ]
        )
        == 0
    )
    assert cli(["--db", db, "tools", "diff", "orders.get_order"]) == 0
    assert '+  "method": "GET"' in capsys.readouterr().out
    assert cli(["--db", db, "tools", "approve", "orders.*"]) == 0
    assert cli(["--db", db, "tools", "enable", "orders.get_order"]) == 0
    assert cli(["--db", db, "tools", "rollback", "orders.get_order"]) == 1  # nothing earlier
    cli(["--db", db, "tools", "list"])
    out = capsys.readouterr().out
    assert "orders.get_order" in out and "enabled" in out and "refund" not in out


def _crawl_orders(db):
    args = ["--db", db, "crawl", "--app", "examples.services.orders:app", "--name", "orders", "--base-url", "http://x"]
    assert cli(args) == 0


def test_cli_bulk_approve_skips_tools_with_nothing_pending(tmp_path, capsys):
    db = str(tmp_path / "b.db")
    _crawl_orders(db)
    assert cli(["--db", db, "tools", "approve", "orders.create_order"]) == 0
    capsys.readouterr()
    # create_order (alphabetically first) has nothing pending; the rest must still be approved
    assert cli(["--db", db, "tools", "approve", "orders.*"]) == 0
    out = capsys.readouterr().out
    assert "orders.create_order: skipped (no pending revision)" in out
    assert "orders.get_order: approved v1" in out
    rows = {t["name"]: t for t in Registry(db).tools("orders")}
    assert all(t["current_version"] == 1 and t["pending"] == 0 for t in rows.values())
    # nothing left to approve at all -> error
    assert cli(["--db", db, "tools", "approve", "orders.*"]) == 1
    assert "no pending revisions" in capsys.readouterr().err
    # glob that matches no tools -> error
    assert cli(["--db", db, "tools", "approve", "nope.*"]) == 1


def test_cli_reject_errors_for_unknown_tool_or_nothing_pending(tmp_path, capsys):
    db = str(tmp_path / "r.db")
    _crawl_orders(db)
    assert cli(["--db", db, "tools", "reject", "orders.does_not_exist"]) == 1
    assert "unknown tool 'orders.does_not_exist'" in capsys.readouterr().err
    assert cli(["--db", db, "tools", "reject", "orders.get_order"]) == 0
    assert "orders.get_order: pending revision rejected" in capsys.readouterr().out
    assert cli(["--db", db, "tools", "reject", "orders.get_order"]) == 1
    assert "no pending revision for 'orders.get_order'" in capsys.readouterr().err


def test_cli_crawl_imports_app_from_current_directory(tmp_path, monkeypatch, capsys):
    import os
    import sys

    pkg = tmp_path / "proj"
    pkg.mkdir()
    (pkg / "cwd_svc_mod.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/ping')\ndef ping() -> dict:\n    return {}\n"
    )
    monkeypatch.chdir(pkg)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", ".", os.getcwd(), str(pkg))])
    monkeypatch.delitem(sys.modules, "cwd_svc_mod", raising=False)
    db = str(tmp_path / "w.db")
    assert cli(["--db", db, "crawl", "--app", "cwd_svc_mod:app", "--name", "svc"]) == 0
    assert "new      svc.ping" in capsys.readouterr().out

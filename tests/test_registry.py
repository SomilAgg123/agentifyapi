import pytest

from agentifyapi.cli import main as cli
from agentifyapi.config import ServiceConfig
from agentifyapi.crawler import crawl_service
from agentifyapi.registry import RegistryError
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

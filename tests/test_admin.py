from fastapi.testclient import TestClient

from agentifyapi import create_app
from agentifyapi.config import ServiceConfig, Settings
from agentifyapi.crawler import crawl_service


def test_admin_ui_review_and_approve(registry):
    crawl_service(registry, ServiceConfig(name="orders", owner="commerce", app="examples.services.orders:app"))
    client = TestClient(create_app(Settings(audit_log=""), registry), client=("127.0.0.1", 50000))
    page = client.get("/admin/")
    assert "orders.get_order" in page.text and "pending" in page.text
    detail = client.get("/admin/tools/orders.get_order")
    assert "proposed" in detail.text and "Approve pending" in detail.text
    assert client.post("/admin/tools/orders.get_order/approve").status_code == 200
    assert client.post("/admin/tools/orders.get_order/enable").status_code == 200
    assert registry.live_definition("orders.get_order")
    assert client.post("/admin/tools/orders.list_orders/enable").status_code == 400


def _app(registry, **admin):
    from agentifyapi.config import AdminConfig

    return create_app(Settings(audit_log="", admin=AdminConfig(**admin)), registry)


def test_admin_ui_default_is_localhost_only(registry, monkeypatch):
    monkeypatch.delenv("AGENTIFYAPI_ADMIN_PASSWORD", raising=False)
    app = _app(registry)
    assert TestClient(app, client=("203.0.113.5", 1234)).get("/admin/").status_code == 403
    assert TestClient(app, client=("127.0.0.1", 1234)).get("/admin/").status_code == 200
    assert TestClient(app, client=("::1", 1234)).get("/admin/").status_code == 200
    # the MCP endpoint's own policy is untouched by the admin gate
    assert TestClient(app, client=("203.0.113.5", 1234)).get("/healthz").status_code == 200


def test_admin_ui_insecure_allow_remote(registry, monkeypatch):
    monkeypatch.delenv("AGENTIFYAPI_ADMIN_PASSWORD", raising=False)
    app = _app(registry, insecure_allow_remote=True)
    assert TestClient(app, client=("203.0.113.5", 1234)).get("/admin/").status_code == 200


def test_admin_ui_basic_auth(registry, monkeypatch):
    monkeypatch.delenv("AGENTIFYAPI_ADMIN_PASSWORD", raising=False)
    app = _app(registry, password="s3cret")
    remote = TestClient(app, client=("203.0.113.5", 1234))
    r = remote.get("/admin/")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    # a password also applies to localhost
    assert TestClient(app, client=("127.0.0.1", 1)).get("/admin/").status_code == 401
    assert remote.get("/admin/", auth=("admin", "nope")).status_code == 401
    assert remote.get("/admin/", auth=("admin", "s3cret")).status_code == 200
    assert remote.post("/admin/tools/x/approve").status_code == 401


def test_admin_password_from_env(registry, monkeypatch):
    monkeypatch.setenv("AGENTIFYAPI_ADMIN_PASSWORD", "envpw")
    remote = TestClient(_app(registry), client=("203.0.113.5", 1234))
    assert remote.get("/admin/").status_code == 401
    assert remote.get("/admin/", auth=("admin", "envpw")).status_code == 200


def test_mount_admin_password(tmp_path, monkeypatch):
    from fastapi import FastAPI

    from agentifyapi import mount

    monkeypatch.delenv("AGENTIFYAPI_ADMIN_PASSWORD", raising=False)
    app = FastAPI()
    mount(app, database=str(tmp_path / "m.db"), audit_log=None, admin_password="pw")
    with TestClient(app, client=("203.0.113.5", 1)) as c:
        assert c.get("/mcp-admin/").status_code == 401
        assert c.get("/mcp-admin/", auth=("admin", "pw")).status_code == 200

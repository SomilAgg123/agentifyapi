from fastapi.testclient import TestClient

from agentifyapi import create_app
from agentifyapi.config import ServiceConfig, Settings
from agentifyapi.crawler import crawl_service


def test_admin_ui_review_and_approve(registry):
    crawl_service(registry, ServiceConfig(name="orders", owner="commerce", app="examples.services.orders:app"))
    client = TestClient(create_app(Settings(audit_log=""), registry))
    page = client.get("/admin/")
    assert "orders.get_order" in page.text and "pending" in page.text
    detail = client.get("/admin/tools/orders.get_order")
    assert "proposed" in detail.text and "Approve pending" in detail.text
    assert client.post("/admin/tools/orders.get_order/approve").status_code == 200
    assert client.post("/admin/tools/orders.get_order/enable").status_code == 200
    assert registry.live_definition("orders.get_order")
    assert client.post("/admin/tools/orders.list_orders/enable").status_code == 400

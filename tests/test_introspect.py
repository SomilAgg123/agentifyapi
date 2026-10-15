from agentifyapi.introspect import import_app, introspect_app
from agentifyapi.schema import spec_to_tools


def test_fastapi_native_introspection():
    app = import_app("examples.services.users:app")
    spec, names = introspect_app(app)
    tools = {t["name"]: t for t in spec_to_tools("users", spec, names)}
    t = tools["users.get_user"]
    assert "loyalty tier" in t["doc"]                        # docstring
    assert t["dependencies"] == ["audit_caller"]             # Depends() graph
    assert t["output_schema"]["properties"]["tier"]["description"].startswith("Loyalty")  # pydantic model
    assert t["tags"] == ["users"]


def test_exclude_flag():
    spec, names = introspect_app(import_app("examples.services.orders:app"))
    assert not any("refund" in t["name"] for t in spec_to_tools("orders", spec, names))

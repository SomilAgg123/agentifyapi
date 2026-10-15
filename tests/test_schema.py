from mcpify.schema import definition_hash, resolve_refs, spec_to_tools, tool_slug

SPEC = {
    "openapi": "3.1.0",
    "paths": {
        "/pets/{pet_id}": {
            "get": {"operationId": "get_pet_pets__pet_id__get", "summary": "Get Pet",
                    "parameters": [{"name": "pet_id", "in": "path", "required": True, "schema": {"type": "integer"}},
                                   {"name": "verbose", "in": "query", "schema": {"type": "boolean"}}],
                    "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}}}},
        },
        "/pets": {"post": {"summary": "Create Pet", "requestBody": {"required": True, "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}}}},
    },
    "components": {"schemas": {"Pet": {"type": "object", "properties": {
        "name": {"type": "string"}, "friend": {"$ref": "#/components/schemas/Pet"}}}}},
}


def test_translation():
    tools = {t["name"]: t for t in spec_to_tools("pets", SPEC)}
    get = tools["pets.get_pet"]
    assert get["method"] == "GET" and get["path_params"] == ["pet_id"] and get["query_params"] == ["verbose"]
    assert get["input_schema"]["required"] == ["pet_id"]
    assert get["output_schema"]["properties"]["name"] == {"type": "string"}
    post = tools["pets.post_pets"]
    assert post["has_body"] and post["input_schema"]["required"] == ["body"]


def test_recursive_ref_is_cut():
    pet = resolve_refs({"$ref": "#/components/schemas/Pet"}, SPEC)
    assert "recursive" in pet["properties"]["friend"]["description"]


def test_slug_and_hash_stability():
    assert tool_slug({"operationId": "list_orders_orders_get"}, "get", "/orders") == "list_orders"
    t = spec_to_tools("pets", SPEC)[0]
    h = definition_hash(t)
    t["description"] = "llm text changes freely"
    assert definition_hash(t) == h
    t["input_schema"]["properties"]["x"] = {"type": "string"}
    assert definition_hash(t) != h

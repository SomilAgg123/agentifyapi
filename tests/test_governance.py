from agentifyapi.config import PolicyConfig
from agentifyapi.governance import is_allowed, project, redact, redact_text, resolve_caller

POLICY = PolicyConfig.model_validate(
    {
        "api_keys": {"k1": {"name": "support", "roles": ["support"]}, "k2": {"name": "bi", "roles": ["readonly"]}},
        "rules": [
            {"tools": ["orders.*"], "roles": ["support"]},
            {"tools": ["orders.get_order"], "roles": ["readonly"]},
        ],
    }
)


def test_policy():
    sup, bi, anon = (resolve_caller(POLICY, k) for k in ("k1", "k2", "nope"))
    assert is_allowed(POLICY, sup, "orders.create_order")
    assert is_allowed(POLICY, bi, "orders.get_order")
    assert not is_allowed(POLICY, bi, "orders.create_order")
    assert not is_allowed(POLICY, sup, "users.get_user")
    assert not is_allowed(POLICY, anon, "orders.get_order")
    assert is_allowed(PolicyConfig(allow_anonymous=True), anon, "x.y")


def test_redaction():
    text, n = redact_text("mail a.b@x.io, call +1 (415) 555-0101, ssn 123-45-6789, card 4242 4242 4242 4242")
    assert n == 4 and "@" not in text and "4242" not in text and "6789" not in text
    assert redact_text("order 1234567890123 total")[1] == 0  # non-Luhn long number kept
    out, n = redact({"u": [{"email": "z@z.com"}], "id": 7})
    assert out == {"u": [{"email": "[REDACTED:email]"}], "id": 7} and n == 1


def test_projection():
    data = {"id": 1, "items": [{"sku": "a", "qty": 2}, {"sku": "b", "qty": 1}], "c": {"n": 1, "m": 2}}
    assert project(data, ["id", "items.sku", "c.m"]) == {"id": 1, "items": [{"sku": "a"}, {"sku": "b"}], "c": {"m": 2}}
    assert project([data], ["id"]) == [{"id": 1}]
    assert project(data, None) is data

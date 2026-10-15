"""Mock orders service."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="orders")


class Item(BaseModel):
    sku: str
    qty: int
    price_cents: int


class Order(BaseModel):
    id: int
    user_id: int
    status: str
    items: list[Item]
    card_number: str
    shipping_note: str = ""


class NewOrder(BaseModel):
    user_id: int
    items: list[Item]


ORDERS = {
    101: Order(id=101, user_id=1, status="shipped", items=[Item(sku="KB-1", qty=1, price_cents=12900)],
               card_number="4242 4242 4242 4242", shipping_note="Call 415-555-0101 on arrival"),
    102: Order(id=102, user_id=2, status="processing", items=[Item(sku="MS-2", qty=2, price_cents=4900)],
               card_number="5555 5555 5555 4444"),
}


@app.get("/orders/{order_id}", response_model=Order, tags=["orders"])
def get_order(order_id: int) -> Order:
    """Look up a single order by id: status, line items, and payment details."""
    if order_id not in ORDERS:
        raise HTTPException(404, "order not found")
    return ORDERS[order_id]


@app.get("/orders", response_model=list[Order], tags=["orders"])
def list_orders(user_id: int | None = None, status: str | None = None) -> list[Order]:
    """List orders, filtered by customer and/or status."""
    return [o for o in ORDERS.values() if (user_id is None or o.user_id == user_id)
            and (status is None or o.status == status)]


@app.post("/orders", response_model=Order, status_code=201, tags=["orders"])
def create_order(order: NewOrder) -> Order:
    """Place a new order for a customer."""
    oid = max(ORDERS) + 1
    ORDERS[oid] = Order(id=oid, status="processing", card_number="on file", **order.model_dump())
    return ORDERS[oid]


@app.post("/orders/{order_id}/refund", tags=["orders"], openapi_extra={"x-mcpify-exclude": True})
def refund_order(order_id: int) -> dict:
    """Internal-only: excluded from MCP via openapi_extra={'x-mcpify-exclude': True}."""
    return {"refunded": order_id}

"""Embed mode: one line adds a governed /mcp endpoint to an existing FastAPI app.

    uvicorn examples.embedded_app:app --port 8200
    agentifyapi --db embedded.db tools list            # review, then approve + enable
"""
from fastapi import FastAPI

from agentifyapi import mount
from agentifyapi.config import PolicyConfig

app = FastAPI(title="inventory")


@app.get("/stock/{sku}")
def get_stock(sku: str) -> dict:
    """Units on hand for a SKU."""
    return {"sku": sku, "on_hand": 42}


mount(app, owner="team-inventory", database="embedded.db",
      policy=PolicyConfig(allow_anonymous=True))  # dev only

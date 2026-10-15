"""The README example: a tiny FastAPI app with a governed MCP endpoint.

Run it:

    uvicorn examples.quickstart:app --port 8200

Then, in another terminal (tools start disabled):

    agentifyapi --db quickstart.db tools list
    agentifyapi --db quickstart.db tools approve inventory.get_stock --by you
    agentifyapi --db quickstart.db tools enable inventory.get_stock

Point an MCP client at http://127.0.0.1:8200/mcp and call invoke_tool
with tool=inventory.get_stock, args={"sku": "KB-1"}.
Or run the whole flow: python scripts/verify_quickstart.py
"""

from fastapi import FastAPI

from agentifyapi import mount
from agentifyapi.config import PolicyConfig

app = FastAPI(title="inventory")


@app.get("/stock/{sku}")
def get_stock(sku: str) -> dict:
    """Units on hand for a SKU."""
    return {"sku": sku, "on_hand": 42, "warehouse": "nyc"}


# Adds /mcp (for agents) and /mcp-admin (for owners). Tools start disabled.
mount(
    app,
    owner="you",
    database="quickstart.db",
    policy=PolicyConfig(allow_anonymous=True),  # local demo; use API keys in production
)

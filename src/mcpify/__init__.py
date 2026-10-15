"""mcpify: make your FastAPI services agent-ready with owner-approved MCP tools."""
from .embed import mount
from .app import create_app

PROJECT_NAME = "mcpify"
__all__ = ["mount", "create_app", "PROJECT_NAME"]
__version__ = "0.1.0"

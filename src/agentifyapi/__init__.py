"""agentifyapi: make your FastAPI services agent-ready with owner-approved MCP tools."""

from importlib.metadata import PackageNotFoundError, version

from .app import create_app
from .embed import mount

PROJECT_NAME = "agentifyapi"
__all__ = ["mount", "create_app", "PROJECT_NAME"]


try:
    __version__ = version("agentifyapi")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0"

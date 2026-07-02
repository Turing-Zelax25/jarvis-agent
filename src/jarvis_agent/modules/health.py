"""Health check tool for the Jarvis Agent MCP server."""
from __future__ import annotations

import importlib.metadata
import platform
import sys
from datetime import datetime, timezone
from typing import Any

import fastmcp

health_server = fastmcp.FastMCP("health")


@health_server.tool()
def health() -> dict[str, Any]:
    """Return server health status.

    Returns a dict with status, version, platform info, and current timestamp.
    No parameters required.
    """
    try:
        version = importlib.metadata.version("jarvis-agent")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0-dev"

    return {
        "status": "ok",
        "version": version,
        "platform": platform.platform(),
        "python_version": sys.version,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

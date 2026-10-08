"""Jarvis Agent MCP server entrypoint.

Starts a FastMCP StreamableHTTP server bound to HOST:PORT,
exposing tool modules: health, pc, browser, printer.

Usage:
    uv run jarvis-agent [--host 0.0.0.0] [--port 8765]

Environment variables:
    JARVIS_HOST         Bind host (default: 0.0.0.0)
    JARVIS_PORT         Bind port (default: 8765)
    JARVIS_LOG_LEVEL    Logging level (default: INFO)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import fastmcp

from jarvis_agent.config import load_config
from jarvis_agent.modules.browser import browser_server
from jarvis_agent.modules.health import health_server
from jarvis_agent.modules.pc import pc_server
from jarvis_agent.modules.printer import printer_server


def build_server() -> fastmcp.FastMCP:
    """Construct and return the main FastMCP server with all modules mounted.

    Returns:
        FastMCP instance with health, pc, browser, and printer sub-servers.
    """
    mcp = fastmcp.FastMCP(
        "jarvis-agent",
        instructions=(
            "Local Jarvis agent for PC control, browser automation, "
            "and 3D printer monitoring on L-0001-01. "
            "Destructive PC actions require JARVIS_REQUIRE_CONFIRM=false."
        ),
    )

    # Mount sub-servers under their respective namespaces (fastmcp 3.x API)
    mcp.mount(health_server, namespace="health")
    mcp.mount(pc_server, namespace="pc")
    mcp.mount(browser_server, namespace="browser")
    mcp.mount(printer_server, namespace="printer")

    return mcp


def main() -> None:
    """CLI entrypoint: parse args, configure logging, and start the server."""
    parser = argparse.ArgumentParser(
        description="Jarvis Agent — StreamableHTTP MCP server"
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind host (overrides JARVIS_HOST env var, default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (overrides JARVIS_PORT env var, default: 8765)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (overrides JARVIS_LOG_LEVEL env var, default: INFO)",
    )
    args = parser.parse_args()

    cfg = load_config()

    # CLI args override environment
    host = args.host or cfg.host
    port = args.port or cfg.port
    log_level = (args.log_level or cfg.log_level).upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger(__name__)
    logger.info(
        "Starting Jarvis Agent MCP server at http://%s:%d/mcp", host, port
    )
    logger.info(
        "Permission gate: JARVIS_REQUIRE_CONFIRM=%s",
        os.environ.get("JARVIS_REQUIRE_CONFIRM", "true"),
    )

    mcp = build_server()
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()

"""Configuration for the Jarvis Agent MCP server.

All settings are read from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """Jarvis Agent runtime configuration."""

    # Server binding
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: str = "INFO"

    # Browser module
    chrome_cdp_url: str = "http://localhost:9222"

    # Printer module (FlashForge Adventurer 3 Pro)
    printer_host: str = "192.168.1.100"
    printer_port: int = 8899

    # Permission gate — set to 'false' to allow destructive PC actions without confirmation
    jarvis_require_confirm: bool = True


def load_config() -> Config:
    """Load configuration from environment variables.

    Returns:
        Config instance populated from env vars or defaults.
    """
    return Config(
        host=os.environ.get("JARVIS_HOST", "0.0.0.0"),
        port=int(os.environ.get("JARVIS_PORT", "8765")),
        log_level=os.environ.get("JARVIS_LOG_LEVEL", "INFO").upper(),
        chrome_cdp_url=os.environ.get("CHROME_CDP_URL", "http://localhost:9222"),
        printer_host=os.environ.get("PRINTER_HOST", "192.168.1.100"),
        printer_port=int(os.environ.get("PRINTER_PORT", "8899")),
        jarvis_require_confirm=os.environ.get(
            "JARVIS_REQUIRE_CONFIRM", "true"
        ).lower() not in ("false", "0", "no"),
    )

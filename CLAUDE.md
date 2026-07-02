# Jarvis Agent — CLAUDE.md

## Project Overview

Python MCP server exposing PC, browser, and 3D-printer control via a
**StreamableHTTP** transport. Deployed on Windows workstation L-0001-01,
accessible from the Hermes VM at `http://100.64.0.2:8765/mcp`.

## Architecture

```
src/jarvis_agent/
  server.py          — FastMCP root server + argparse entrypoint
  config.py          — Env-var config dataclass (load_config())
  modules/
    health.py        — health tool (health_server, mounted at "health")
    pc.py            — pc_launch_app, pc_open_file, pc_screenshot, pc_media_key
    browser.py       — browser_navigate, browser_get_page_text, browser_click, etc.
    printer.py       — printer_status, printer_progress, printer_temp, printer_info
tests/
  test_health.py
  test_printer.py
```

## Tech Stack

- **Framework**: fastmcp >= 2.0
- **Transport**: StreamableHTTP (stateless, bound to JARVIS_HOST:JARVIS_PORT)
- **Optional**: playwright (browser module), pywin32 / ctypes (media keys on Windows)
- **Package manager**: uv (pyproject.toml)
- **Python**: 3.11+

## Key Commands

```bash
# Install deps
uv sync

# Run server (dev mode, all interfaces)
uv run jarvis-agent --port 8765

# Run server bound to Tailscale interface only
JARVIS_HOST=100.64.0.2 uv run jarvis-agent --port 8765

# Run tests
uv run pytest

# Install Playwright browsers (optional, for browser module)
uv add 'jarvis-agent[browser]'
uv run playwright install chromium
```

## Environment Variables

| Variable               | Default           | Description                                    |
|------------------------|-------------------|------------------------------------------------|
| `JARVIS_HOST`          | `0.0.0.0`         | Bind address                                   |
| `JARVIS_PORT`          | `8765`            | Bind port                                      |
| `JARVIS_LOG_LEVEL`     | `INFO`            | Logging level                                  |
| `JARVIS_REQUIRE_CONFIRM` | `true`          | Block destructive PC actions until set to false |
| `CHROME_CDP_URL`       | `http://localhost:9222` | Chrome remote debugging endpoint          |
| `PRINTER_HOST`         | `192.168.1.100`   | FlashForge printer IP                          |
| `PRINTER_PORT`         | `8899`            | FlashForge M-code TCP port                     |

## Code Conventions

- Full type annotations on all public functions
- Docstrings: Google-style on all modules, classes, and tools
- No print() — use `logging.getLogger(__name__)`
- Optional deps (playwright, pywin32): guarded with try/except ImportError
- All network I/O: explicit timeouts
- Permission gate: `_permission_gate()` before destructive PC actions

## Deployment (Windows / L-0001-01)

1. Install Python 3.11+ and uv
2. Clone repo, run `uv sync`
3. Set environment variables (JARVIS_REQUIRE_CONFIRM, PRINTER_HOST, etc.)
4. Start: `uv run jarvis-agent --host 100.64.0.2 --port 8765`
5. Windows Firewall: allow TCP 8765 from Tailscale subnet 100.64.0.0/10
6. Register in Hermes config.yaml under mcp_servers

## Hermes MCP Registration

Add to `~/.hermes/config.yaml`:
```yaml
mcp_servers:
  jarvis:
    url: http://100.64.0.2:8765/mcp
    transport: streamable-http
```

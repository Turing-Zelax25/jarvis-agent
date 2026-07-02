# Jarvis Agent

Local Jarvis agent for L-0001-01 — a **StreamableHTTP MCP server** exposing PC control,
Chrome browser automation, and FlashForge 3D printer monitoring.

Hermes connects to this server at `http://100.64.0.2:8765/mcp` via the Tailscale network.

---

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. (Optional) Install browser automation support
uv add "jarvis-agent[browser]"
uv run playwright install chromium

# 3. Start the server
uv run jarvis-agent --host 100.64.0.2 --port 8765
```

The server starts and logs to stderr:
```
2026-07-02 10:00:00 INFO     Starting Jarvis Agent MCP server at http://100.64.0.2:8765/mcp
```

---

## Configuration

All settings via environment variables:

| Variable               | Default                 | Description                                           |
|------------------------|-------------------------|-------------------------------------------------------|
| `JARVIS_HOST`          | `0.0.0.0`               | Bind address (set to `100.64.0.2` for Tailscale-only) |
| `JARVIS_PORT`          | `8765`                  | TCP port                                              |
| `JARVIS_LOG_LEVEL`     | `INFO`                  | `DEBUG`, `INFO`, `WARNING`, `ERROR`                   |
| `JARVIS_REQUIRE_CONFIRM` | `true`                | Block destructive PC actions. Set to `false` to allow |
| `CHROME_CDP_URL`       | `http://localhost:9222` | Chrome `--remote-debugging-port` endpoint             |
| `PRINTER_HOST`         | `192.168.1.100`         | FlashForge Adventurer 3 Pro LAN IP                    |
| `PRINTER_PORT`         | `8899`                  | FlashForge M-code TCP port                            |

---

## Tool Modules

### `health.*`
| Tool     | Description                                         |
|----------|-----------------------------------------------------|
| `health_health` | Server health check — version, platform, timestamp |

### `pc.*`
| Tool              | Description                                             |
|-------------------|---------------------------------------------------------|
| `pc_pc_launch_app` | Launch an application by name (gated by permission)   |
| `pc_pc_open_file`  | Open a file with its default application              |
| `pc_pc_screenshot` | Take a screenshot → base64 PNG                        |
| `pc_pc_media_key`  | Send media key (play/pause, next, prev, vol, mute) (gated) |

### `browser.*`
| Tool                      | Description                                   |
|---------------------------|-----------------------------------------------|
| `browser_browser_navigate`       | Navigate to a URL                      |
| `browser_browser_get_page_text`  | Extract page text content              |
| `browser_browser_click`          | Click element by CSS selector          |
| `browser_browser_type`           | Type text into an input element        |
| `browser_browser_screenshot`     | Screenshot the current page → base64 PNG |

> Requires Playwright. Install with `uv add 'jarvis-agent[browser]'` then `playwright install chromium`.
> Chrome must be launched with `--remote-debugging-port=9222`.

### `printer.*`
| Tool                     | Description                                    |
|--------------------------|------------------------------------------------|
| `printer_printer_status`   | Machine state (M119)                         |
| `printer_printer_progress` | SD print progress (M27)                      |
| `printer_printer_temp`     | Extruder + bed temperatures (M105)           |
| `printer_printer_info`     | Firmware info (M115)                         |

---

## Windows Deployment

### Firewall Rule (Tailscale subnet only)

Run as Administrator — allows TCP 8765 only from the Tailscale CGNAT range:

```powershell
netsh advfirewall firewall add rule ^
  name="Jarvis Agent MCP (Tailscale)" ^
  dir=in action=allow protocol=TCP ^
  localport=8765 ^
  remoteip=100.64.0.0/255.192.0.0
```

### Tailscale Binding

Bind to the Tailscale interface IP so the port is not exposed on LAN:

```powershell
$env:JARVIS_HOST = "100.64.0.2"
$env:JARVIS_PORT = "8765"
$env:JARVIS_REQUIRE_CONFIRM = "false"
uv run jarvis-agent
```

### NSSM Service (future)

A follow-up task will configure NSSM to run `jarvis-agent` as a Windows service
for unattended operation.

---

## Hermes MCP Registration

After the server is running on L-0001-01, register it in the Hermes Agent config
on the Hermes VM (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  jarvis:
    url: http://100.64.0.2:8765/mcp
    transport: streamable-http
```

Verify with: `hermes tools` — the `health_health` tool should appear.

---

## Development

```bash
# Run tests
uv run pytest

# Run with verbose logging
JARVIS_LOG_LEVEL=DEBUG uv run jarvis-agent --port 8765

# Disable permission gate for local testing
JARVIS_REQUIRE_CONFIRM=false uv run jarvis-agent
```

---

## Architecture

```
src/jarvis_agent/
  server.py          Main FastMCP server + argparse entrypoint
  config.py          Env-var config dataclass
  modules/
    health.py        health tool
    pc.py            PC control tools (launch, open, screenshot, media)
    browser.py       Browser automation via Playwright / CDP
    printer.py       FlashForge M-code TCP client
tests/
  test_health.py
  test_printer.py
```

Transport: StreamableHTTP (stateless).
Each tool module is a `FastMCP` instance mounted on the root server.

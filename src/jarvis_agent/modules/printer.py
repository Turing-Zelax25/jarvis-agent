"""FlashForge Adventurer 3 Pro control tools for the Jarvis Agent MCP server.

Communicates via raw TCP socket on port 8899 using M-code (G-code extended) protocol.
All tool calls create a fresh TCP connection per request — no persistent state.
"""
from __future__ import annotations

import logging
import os
import re
import socket
from typing import Any

import fastmcp
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

printer_server = fastmcp.FastMCP("printer")

_SOCKET_TIMEOUT = 5.0  # seconds


def _get_printer_addr() -> tuple[str, int]:
    """Return (host, port) for the printer from environment variables."""
    host = os.environ.get("PRINTER_HOST", "192.168.1.100")
    port = int(os.environ.get("PRINTER_PORT", "8899"))
    return host, port


def _send_mcodes(codes: list[str]) -> str:
    """Send one or more M-codes to the printer and return the response.

    Args:
        codes: List of M-code strings (e.g. ['M115', 'M119']).

    Returns:
        Raw response string from the printer.

    Raises:
        ToolError: On connection failure or timeout.
    """
    host, port = _get_printer_addr()
    payload = "\r\n".join(codes) + "\r\n"

    try:
        with socket.create_connection((host, port), timeout=_SOCKET_TIMEOUT) as sock:
            sock.sendall(payload.encode("ascii"))
            chunks: list[bytes] = []
            sock.settimeout(_SOCKET_TIMEOUT)
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    # Stop reading when we see 'ok' or 'CMD' followed by newline
                    combined = b"".join(chunks).decode("ascii", errors="replace")
                    if "\nok\n" in combined or combined.strip().endswith("ok"):
                        break
                except socket.timeout:
                    break
            return b"".join(chunks).decode("ascii", errors="replace").strip()
    except ConnectionRefusedError as exc:
        raise ToolError(
            f"Cannot connect to printer at {host}:{port} — connection refused. "
            "Check PRINTER_HOST / PRINTER_PORT and that the printer is on."
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ToolError(
            f"Timeout communicating with printer at {host}:{port}. "
            "Check network connectivity."
        ) from exc
    except OSError as exc:
        raise ToolError(f"Network error communicating with printer: {exc}") from exc


# ── Tools ──────────────────────────────────────────────────────────────────────


@printer_server.tool()
def printer_status() -> dict[str, Any]:
    """Query printer machine state via M119.

    Returns:
        dict with 'machine_status', 'move_mode', 'endstop_info', and 'raw' fields.
    """
    logger.info("Querying printer status (M119)")
    raw = _send_mcodes(["M119"])

    # Parse FlashForge M119 response format:
    # CMD M119 Received.
    # Endstop: X-max:0 Y-max:0 Z-min:1
    # MachineStatus: READY
    # MoveMode: READY
    # Status: S:1 L:0 J:0 F:0
    # LED: 0
    # CurrentFile: ...
    machine_status = "UNKNOWN"
    move_mode = "UNKNOWN"
    endstop_info: dict[str, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("MachineStatus:"):
            machine_status = line.split(":", 1)[1].strip()
        elif line.startswith("MoveMode:"):
            move_mode = line.split(":", 1)[1].strip()
        elif line.startswith("Endstop:"):
            # Parse "X-max:0 Y-max:0 Z-min:1"
            endstop_raw = line.split(":", 1)[1].strip()
            for part in endstop_raw.split():
                if ":" in part:
                    k, v = part.split(":", 1)
                    endstop_info[k] = v

    return {
        "machine_status": machine_status,
        "move_mode": move_mode,
        "endstop_info": endstop_info,
        "raw": raw,
    }


@printer_server.tool()
def printer_progress() -> dict[str, Any]:
    """Query SD print progress via M27.

    Returns:
        dict with 'printing' (bool), 'current_byte', 'total_bytes', 'percent_complete', 'raw'.
    """
    logger.info("Querying printer progress (M27)")
    raw = _send_mcodes(["M27"])

    # Parse: "SD printing byte 12345/67890" or "Not SD printing."
    printing = False
    current_byte = 0
    total_bytes = 0
    percent_complete = 0.0

    for line in raw.splitlines():
        line = line.strip()
        m = re.search(r"SD printing byte (\d+)/(\d+)", line)
        if m:
            printing = True
            current_byte = int(m.group(1))
            total_bytes = int(m.group(2))
            if total_bytes > 0:
                percent_complete = round(current_byte / total_bytes * 100, 1)
            break
        if "Not SD printing" in line:
            printing = False
            break

    return {
        "printing": printing,
        "current_byte": current_byte,
        "total_bytes": total_bytes,
        "percent_complete": percent_complete,
        "raw": raw,
    }


@printer_server.tool()
def printer_temp() -> dict[str, Any]:
    """Query printer temperatures via M105.

    Returns:
        dict with 'extruder_temp', 'extruder_target', 'bed_temp', 'bed_target', 'raw'.
    """
    logger.info("Querying printer temperatures (M105)")
    raw = _send_mcodes(["M105"])

    # Parse: "T0:210 /210 B:60 /60" (current / target)
    extruder_temp = 0.0
    extruder_target = 0.0
    bed_temp = 0.0
    bed_target = 0.0

    for line in raw.splitlines():
        # Match T0:CURRENT /TARGET
        t0 = re.search(r"T0:([\d.]+)\s*/\s*([\d.]+)", line)
        if t0:
            extruder_temp = float(t0.group(1))
            extruder_target = float(t0.group(2))
        # Match B:CURRENT /TARGET
        b = re.search(r"B:([\d.]+)\s*/\s*([\d.]+)", line)
        if b:
            bed_temp = float(b.group(1))
            bed_target = float(b.group(2))

    return {
        "extruder_temp": extruder_temp,
        "extruder_target": extruder_target,
        "bed_temp": bed_temp,
        "bed_target": bed_target,
        "raw": raw,
    }


@printer_server.tool()
def printer_info() -> dict[str, Any]:
    """Query printer firmware info via M115.

    Returns:
        dict with 'raw' response and any parsed key-value pairs.
    """
    logger.info("Querying printer info (M115)")
    raw = _send_mcodes(["M115"])

    # Try to parse KEY:VALUE pairs
    info: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("CMD") and line != "ok":
            k, _, v = line.partition(":")
            info[k.strip()] = v.strip()

    return {"info": info, "raw": raw}

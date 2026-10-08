"""PC control tools for the Jarvis Agent MCP server.

Provides app launch, file open, screenshot, and media key control.
All destructive actions are gated behind the JARVIS_REQUIRE_CONFIRM permission.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import platform
import subprocess
import sys
from typing import Any

import fastmcp
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

pc_server = fastmcp.FastMCP("pc")

# ── Permission gate ────────────────────────────────────────────────────────────


def _permission_gate(tool_name: str, params_summary: str) -> None:
    """Raise ToolError if JARVIS_REQUIRE_CONFIRM is set to true.

    Args:
        tool_name: Name of the tool requesting permission.
        params_summary: Human-readable summary of the action parameters.

    Raises:
        ToolError: If confirmation is required but not given.
    """
    require = os.environ.get("JARVIS_REQUIRE_CONFIRM", "true").lower()
    if require not in ("false", "0", "no"):
        raise ToolError(
            f"Permission required for '{tool_name}' ({params_summary}). "
            "Set JARVIS_REQUIRE_CONFIRM=false to allow without confirmation, "
            "or implement the confirmation flow."
        )


# ── Tools ──────────────────────────────────────────────────────────────────────


@pc_server.tool()
def pc_launch_app(app_name: str, args: list[str] | None = None) -> dict[str, Any]:
    """Launch an application by name.

    Requires JARVIS_REQUIRE_CONFIRM=false to execute.

    Args:
        app_name: Name or full path of the executable to launch.
        args: Optional list of command-line arguments.

    Returns:
        dict with 'pid', 'status', and 'command' fields.
    """
    args = args or []
    _permission_gate("pc_launch_app", f"app_name={app_name!r}")

    cmd = [app_name, *args]
    # shell=False everywhere: CreateProcess on Windows still resolves a bare
    # executable name via PATH when given as a list, so this does not lose
    # the "launch by name" behavior. Using shell=True with a naive " ".join()
    # let any arg containing &, |, or && break out into a second shell
    # command (Windows shell-injection via pc_launch_app args).
    logger.info("Launching app: %s", cmd)

    try:
        proc = subprocess.Popen(
            cmd,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"pid": proc.pid, "status": "launched", "command": cmd}
    except FileNotFoundError as exc:
        raise ToolError(f"Executable not found: {app_name!r}") from exc
    except OSError as exc:
        raise ToolError(f"Failed to launch {app_name!r}: {exc}") from exc


@pc_server.tool()
def pc_open_file(path: str) -> dict[str, str]:
    """Open a file with its default application.

    Requires JARVIS_REQUIRE_CONFIRM=false to execute. On Windows,
    os.startfile() runs the path's registered handler — for an
    .exe/.bat/.cmd/.ps1/.vbs/.lnk that is arbitrary code execution, not a
    benign "open a document" action, so this is gated the same as
    pc_launch_app and pc_media_key.

    Args:
        path: Absolute or relative path to the file.

    Returns:
        dict with 'status' and 'path' fields.
    """
    _permission_gate("pc_open_file", f"path={path!r}")
    logger.info("Opening file: %s", path)
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"status": "opened", "path": path}
    except AttributeError:
        # os.startfile not available on non-Windows
        raise ToolError(f"os.startfile not available on {system}") from None
    except OSError as exc:
        raise ToolError(f"Failed to open {path!r}: {exc}") from exc


@pc_server.tool()
def pc_screenshot(display: int = 0) -> dict[str, Any]:
    """Take a screenshot and return it as a base64-encoded PNG.

    Args:
        display: Display index (only used on Linux with scrot; ignored elsewhere).

    Returns:
        dict with 'image_b64' (base64 PNG), 'width', 'height', and 'format' fields.
    """
    logger.info("Taking screenshot (display=%d)", display)
    system = platform.system()

    try:
        from PIL import Image, ImageGrab  # type: ignore[import-untyped]

        if system in ("Windows", "Darwin"):
            img: Image.Image = ImageGrab.grab()
        else:
            # Linux: try PIL first (requires Xlib), fall back to scrot
            try:
                img = ImageGrab.grab()
            except Exception:
                # Fallback: use scrot to capture to a temp file
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                subprocess.run(["scrot", "-d", "0", tmp_path], check=True, timeout=10)
                img = Image.open(tmp_path)
                os.unlink(tmp_path)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return {
            "image_b64": base64.b64encode(buf.getvalue()).decode(),
            "width": img.width,
            "height": img.height,
            "format": "png",
        }

    except ImportError:
        raise ToolError(
            "Pillow is not installed. Install it with: uv add pillow"
        ) from None
    except subprocess.CalledProcessError as exc:
        raise ToolError(f"scrot screenshot failed: {exc}") from exc


# Media key VK codes for Windows (ctypes)
_WIN_VK_MAP: dict[str, int] = {
    "play_pause": 0xB3,
    "next_track": 0xB0,
    "prev_track": 0xB1,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}

_VALID_KEYS = list(_WIN_VK_MAP.keys())


@pc_server.tool()
def pc_media_key(key: str) -> dict[str, str]:
    """Send a media key event to the OS.

    Requires JARVIS_REQUIRE_CONFIRM=false to execute.

    Args:
        key: One of: play_pause, next_track, prev_track, volume_up, volume_down, mute.

    Returns:
        dict with 'status' and 'key' fields.
    """
    if key not in _WIN_VK_MAP:
        raise ToolError(
            f"Unknown media key {key!r}. Valid keys: {', '.join(_VALID_KEYS)}"
        )
    _permission_gate("pc_media_key", f"key={key!r}")

    system = platform.system()
    logger.info("Sending media key: %s (platform=%s)", key, system)

    if system == "Windows":
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        vk = _WIN_VK_MAP[key]
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)  # type: ignore[attr-defined]
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)  # type: ignore[attr-defined]

    elif system == "Darwin":
        # Use osascript for macOS
        mac_map = {
            "play_pause": "key code 49",
            "next_track": "key code 124",
            "prev_track": "key code 123",
            "volume_up": "key code 72",
            "volume_down": "key code 73",
            "mute": "key code 74",
        }
        script = f'tell application "System Events" to {mac_map[key]}'
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)

    else:
        # Linux: use xdotool
        xdg_map = {
            "play_pause": "XF86AudioPlay",
            "next_track": "XF86AudioNext",
            "prev_track": "XF86AudioPrev",
            "volume_up": "XF86AudioRaiseVolume",
            "volume_down": "XF86AudioLowerVolume",
            "mute": "XF86AudioMute",
        }
        subprocess.run(
            ["xdotool", "key", xdg_map[key]], check=True, timeout=5
        )

    return {"status": "sent", "key": key}

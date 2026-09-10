"""Tests for the Jarvis Agent pc module.

Covers pc_launch_app, pc_open_file, pc_screenshot, pc_media_key,
and the _permission_gate helper. All subprocess/OS calls are mocked.
"""
from __future__ import annotations

import base64
import io
import os
import platform
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _small_png_bytes() -> bytes:
    """Return a minimal valid PNG as bytes via Pillow."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Permission gate ─────────────────────────────────────────────────────────────


def test_permission_gate_blocks_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """_permission_gate should raise ToolError when JARVIS_REQUIRE_CONFIRM is unset."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.delenv("JARVIS_REQUIRE_CONFIRM", raising=False)

    with pytest.raises(ToolError, match="Permission required"):
        _permission_gate("test_tool", "param=value")


def test_permission_gate_blocks_when_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """_permission_gate should raise ToolError when JARVIS_REQUIRE_CONFIRM=true."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        _permission_gate("test_tool", "param=value")


def test_permission_gate_passes_when_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """_permission_gate should NOT raise when JARVIS_REQUIRE_CONFIRM=false."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    # Should not raise
    _permission_gate("test_tool", "param=value")


def test_permission_gate_passes_when_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """_permission_gate should NOT raise when JARVIS_REQUIRE_CONFIRM=0."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "0")

    _permission_gate("test_tool", "param=value")


def test_permission_gate_passes_when_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """_permission_gate should NOT raise when JARVIS_REQUIRE_CONFIRM=no."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "no")

    _permission_gate("test_tool", "param=value")


# ── pc_launch_app ──────────────────────────────────────────────────────────────


def test_pc_launch_app_returns_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should return pid and status='launched' on success."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        result = pc_launch_app("notepad.exe", args=["file.txt"])

    assert result["status"] == "launched"
    assert result["pid"] == 12345
    assert "notepad.exe" in result["command"]
    assert "file.txt" in result["command"]
    mock_popen.assert_called_once()


def test_pc_launch_app_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should work when no args are provided."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    mock_proc = MagicMock()
    mock_proc.pid = 999

    with patch("subprocess.Popen", return_value=mock_proc):
        result = pc_launch_app("calc.exe")

    assert result["status"] == "launched"
    assert result["pid"] == 999


def test_pc_launch_app_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError when executable is not found."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
        with pytest.raises(ToolError, match="not found"):
            pc_launch_app("nonexistent_app")


def test_pc_launch_app_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError on OSError."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    with patch("subprocess.Popen", side_effect=OSError("permission denied")):
        with pytest.raises(ToolError, match="Failed to launch"):
            pc_launch_app("restricted_app")


def test_pc_launch_app_permission_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError when JARVIS_REQUIRE_CONFIRM=true."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        pc_launch_app("anything.exe")


# ── pc_open_file ───────────────────────────────────────────────────────────────


def test_pc_open_file_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should use xdg-open on Linux."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_open_file

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("subprocess.Popen") as mock_popen:
        result = pc_open_file("/tmp/report.pdf")

    assert result["status"] == "opened"
    assert result["path"] == "/tmp/report.pdf"
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args[0] == "xdg-open"
    assert "/tmp/report.pdf" in args


def test_pc_open_file_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should use 'open' on macOS."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_open_file

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    with patch("subprocess.Popen") as mock_popen:
        result = pc_open_file("/Users/me/doc.pdf")

    assert result["status"] == "opened"
    args = mock_popen.call_args[0][0]
    assert args[0] == "open"


def test_pc_open_file_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should use os.startfile on Windows."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_open_file
    import jarvis_agent.modules.pc as pc_mod

    monkeypatch.setattr(platform, "system", lambda: "Windows")

    # os.startfile doesn't exist on Linux; inject it into the module's os reference
    mock_startfile = MagicMock()
    monkeypatch.setattr(pc_mod.os, "startfile", mock_startfile, raising=False)

    result = pc_open_file(r"C:\docs\report.pdf")

    assert result["status"] == "opened"
    mock_startfile.assert_called_once_with(r"C:\docs\report.pdf")


def test_pc_open_file_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should raise ToolError on OSError."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_open_file

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("subprocess.Popen", side_effect=OSError("permission denied")):
        with pytest.raises(ToolError, match="Failed to open"):
            pc_open_file("/restricted/file.pdf")


# ── pc_screenshot ──────────────────────────────────────────────────────────────


def test_pc_screenshot_returns_base64_png(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_screenshot should return a base64-encoded PNG with metadata."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_screenshot
    from PIL import Image

    fake_img = Image.new("RGB", (100, 80), color=(0, 128, 255))

    with patch("PIL.ImageGrab.grab", return_value=fake_img):
        monkeypatch.setattr(platform, "system", lambda: "Darwin")
        result = pc_screenshot()

    assert result["format"] == "png"
    assert result["width"] == 100
    assert result["height"] == 80
    assert "image_b64" in result
    # Verify the base64 decodes to a valid PNG
    raw = base64.b64decode(result["image_b64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_pc_screenshot_linux_pillow_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_screenshot on Linux should succeed when PIL.ImageGrab.grab works."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_screenshot
    from PIL import Image

    fake_img = Image.new("RGB", (50, 50), color=(255, 255, 0))

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("PIL.ImageGrab.grab", return_value=fake_img):
        result = pc_screenshot()

    assert result["width"] == 50
    assert result["height"] == 50


def test_pc_screenshot_linux_scrot_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_screenshot on Linux should fall back to scrot if ImageGrab fails."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_screenshot
    from PIL import Image

    fake_img = Image.new("RGB", (640, 480), color=(0, 0, 0))

    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("PIL.ImageGrab.grab", side_effect=OSError("no display")):
        with patch("subprocess.run"):
            with patch("PIL.Image.open", return_value=fake_img):
                with patch("os.unlink"):
                    result = pc_screenshot()

    assert result["width"] == 640
    assert result["height"] == 480


# ── pc_media_key ───────────────────────────────────────────────────────────────


def test_pc_media_key_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key should raise ToolError for unknown key names."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    with pytest.raises(ToolError, match="Unknown media key"):
        pc_media_key("turbo_boost")


def test_pc_media_key_permission_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key should raise ToolError when JARVIS_REQUIRE_CONFIRM=true."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        pc_media_key("play_pause")


def test_pc_media_key_linux_xdotool(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key on Linux should call xdotool with the correct key name."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("subprocess.run") as mock_run:
        result = pc_media_key("play_pause")

    assert result["status"] == "sent"
    assert result["key"] == "play_pause"
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "xdotool"
    assert "XF86AudioPlay" in cmd


def test_pc_media_key_darwin_osascript(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key on macOS should call osascript."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    with patch("subprocess.run") as mock_run:
        result = pc_media_key("volume_up")

    assert result["status"] == "sent"
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "osascript"


def test_pc_media_key_windows_ctypes(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key on Windows should call keybd_event via ctypes."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(platform, "system", lambda: "Windows")

    # Mock ctypes.windll (not available on Linux)
    mock_user32 = MagicMock()
    mock_windll = MagicMock()
    mock_windll.user32 = mock_user32
    mock_ctypes = MagicMock()
    mock_ctypes.windll = mock_windll

    with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
        result = pc_media_key("mute")

    assert result["status"] == "sent"
    assert result["key"] == "mute"
    # keybd_event should have been called for keydown + keyup
    assert mock_user32.keybd_event.call_count == 2


@pytest.mark.parametrize("key", ["play_pause", "next_track", "prev_track", "volume_up", "volume_down", "mute"])
def test_pc_media_key_all_valid_keys_linux(key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key should accept all documented valid keys."""
    pytest.importorskip("fastmcp")
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    with patch("subprocess.run"):
        result = pc_media_key(key)

    assert result["key"] == key
    assert result["status"] == "sent"

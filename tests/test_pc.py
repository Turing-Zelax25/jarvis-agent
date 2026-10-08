"""Tests for the Jarvis Agent pc module.

Uses unittest.mock to avoid real subprocess/ctypes/file-handler side effects.
"""
from __future__ import annotations

import os

import pytest
from unittest.mock import MagicMock, patch


# ── _permission_gate ─────────────────────────────────────────────────────────


def test_permission_gate_blocks_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate should block when JARVIS_REQUIRE_CONFIRM is unset."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.delenv("JARVIS_REQUIRE_CONFIRM", raising=False)

    with pytest.raises(ToolError, match="Permission required"):
        _permission_gate("some_tool", "params")


def test_permission_gate_blocks_when_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate should block when JARVIS_REQUIRE_CONFIRM=true."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        _permission_gate("some_tool", "params")


@pytest.mark.parametrize("value", ["false", "0", "no", "False", "NO"])
def test_permission_gate_allows_when_falsy(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Gate should allow when JARVIS_REQUIRE_CONFIRM is false/0/no (any case)."""
    pytest.importorskip("fastmcp")

    from jarvis_agent.modules.pc import _permission_gate

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", value)

    # Should not raise.
    _permission_gate("some_tool", "params")


# ── pc_launch_app ─────────────────────────────────────────────────────────────


def test_pc_launch_app_blocked_by_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError when the gate is closed."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        pc_launch_app("notepad.exe")


def test_pc_launch_app_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should Popen the executable and return its pid, shell=False."""
    pytest.importorskip("fastmcp")

    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    fake_proc = MagicMock()
    fake_proc.pid = 1234

    with patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
        result = pc_launch_app("notepad.exe", args=["foo.txt"])

    assert result == {
        "pid": 1234,
        "status": "launched",
        "command": ["notepad.exe", "foo.txt"],
    }
    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args
    assert call_args[0] == ["notepad.exe", "foo.txt"]
    assert call_kwargs.get("shell") is False


def test_pc_launch_app_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError when the executable is missing."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    with patch("subprocess.Popen", side_effect=FileNotFoundError()):
        with pytest.raises(ToolError, match="Executable not found"):
            pc_launch_app("does-not-exist.exe")


def test_pc_launch_app_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_launch_app should raise ToolError on a generic OSError."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_launch_app

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")

    with patch("subprocess.Popen", side_effect=OSError("boom")):
        with pytest.raises(ToolError, match="Failed to launch"):
            pc_launch_app("notepad.exe")


# ── pc_open_file ──────────────────────────────────────────────────────────────


def test_pc_open_file_blocked_by_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should be gated identically to pc_launch_app (regression:
    previously ungated, letting os.startfile() execute .exe/.bat/.ps1 paths
    with no confirmation).
    """
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_open_file

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        pc_open_file("C:\\Users\\test\\document.pdf")


def test_pc_open_file_success_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should call os.startfile on Windows once the gate is open."""
    pytest.importorskip("fastmcp")

    import jarvis_agent.modules.pc as pc_mod

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(pc_mod.platform, "system", lambda: "Windows")

    fake_startfile = MagicMock()
    monkeypatch.setattr(pc_mod.os, "startfile", fake_startfile, raising=False)

    result = pc_mod.pc_open_file("C:\\file.txt")

    assert result == {"status": "opened", "path": "C:\\file.txt"}
    fake_startfile.assert_called_once_with("C:\\file.txt")


def test_pc_open_file_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_open_file should raise ToolError when the OS call fails."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    import jarvis_agent.modules.pc as pc_mod

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(pc_mod.platform, "system", lambda: "Linux")

    with patch("subprocess.Popen", side_effect=OSError("no such file")):
        with pytest.raises(ToolError, match="Failed to open"):
            pc_mod.pc_open_file("/tmp/nope")


# ── pc_media_key ──────────────────────────────────────────────────────────────


def test_pc_media_key_invalid_key() -> None:
    """pc_media_key should raise ToolError for an unknown key (gate not reached)."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_media_key

    with pytest.raises(ToolError, match="Unknown media key"):
        pc_media_key("not_a_real_key")


def test_pc_media_key_blocked_by_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key should be blocked by the permission gate for a valid key."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_media_key

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "true")

    with pytest.raises(ToolError, match="Permission required"):
        pc_media_key("mute")


def test_pc_media_key_sends_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_media_key should invoke ctypes keybd_event on Windows."""
    pytest.importorskip("fastmcp")

    import jarvis_agent.modules.pc as pc_mod

    monkeypatch.setenv("JARVIS_REQUIRE_CONFIRM", "false")
    monkeypatch.setattr(pc_mod.platform, "system", lambda: "Windows")

    fake_user32 = MagicMock()
    fake_windll = MagicMock(user32=fake_user32)

    import ctypes

    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)

    result = pc_mod.pc_media_key("mute")

    assert result == {"status": "sent", "key": "mute"}
    assert fake_user32.keybd_event.call_count == 2


# ── pc_screenshot ─────────────────────────────────────────────────────────────


def test_pc_screenshot_import_error_when_pillow_missing() -> None:
    """pc_screenshot should raise a helpful ToolError when Pillow is absent."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.pc import pc_screenshot

    with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None, "PIL.ImageGrab": None}):
        with pytest.raises(ToolError, match="Pillow is not installed"):
            pc_screenshot()


def test_pc_screenshot_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """pc_screenshot should return a base64 PNG + dimensions on success."""
    pytest.importorskip("fastmcp")
    PIL = pytest.importorskip("PIL")

    import jarvis_agent.modules.pc as pc_mod

    monkeypatch.setattr(pc_mod.platform, "system", lambda: "Windows")

    fake_img = MagicMock()
    fake_img.width = 1920
    fake_img.height = 1080

    def _fake_save(buf, format=None):
        buf.write(b"\x89PNG\r\n\x1a\n")

    fake_img.save.side_effect = _fake_save

    with patch("PIL.ImageGrab.grab", return_value=fake_img):
        result = pc_mod.pc_screenshot()

    assert result["format"] == "png"
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert "image_b64" in result

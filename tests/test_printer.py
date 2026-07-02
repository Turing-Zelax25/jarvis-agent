"""Tests for the Jarvis Agent printer module.

Uses unittest.mock to avoid needing a real FlashForge printer.
"""
from __future__ import annotations

import socket
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_mock_socket(response_bytes: bytes) -> MagicMock:
    """Create a mock socket that returns a fixed response."""
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = [response_bytes, b""]
    mock_sock.__enter__ = lambda s: s
    mock_sock.__exit__ = MagicMock(return_value=False)
    return mock_sock


# ── _send_mcodes ───────────────────────────────────────────────────────────────


def test_send_mcodes_sends_payload() -> None:
    """_send_mcodes should send the M-code payload to the socket."""
    pytest.importorskip("fastmcp")

    response = b"CMD M115 Received.\r\nFIRMWARE_NAME:FlashForge\r\nok\n"
    mock_sock = _make_mock_socket(response)

    with patch("socket.create_connection", return_value=mock_sock):
        from jarvis_agent.modules.printer import _send_mcodes

        result = _send_mcodes(["M115"])

    mock_sock.sendall.assert_called_once()
    payload_sent = mock_sock.sendall.call_args[0][0].decode("ascii")
    assert "M115" in payload_sent
    assert "FIRMWARE_NAME" in result


def test_send_mcodes_connection_refused() -> None:
    """_send_mcodes should raise ToolError on connection refused."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.printer import _send_mcodes

    with patch(
        "socket.create_connection",
        side_effect=ConnectionRefusedError("Connection refused"),
    ):
        with pytest.raises(ToolError, match="connection refused"):
            _send_mcodes(["M119"])


def test_send_mcodes_timeout() -> None:
    """_send_mcodes should raise ToolError on socket timeout."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    from jarvis_agent.modules.printer import _send_mcodes

    with patch("socket.create_connection", side_effect=socket.timeout("timed out")):
        with pytest.raises(ToolError, match="Timeout"):
            _send_mcodes(["M27"])


# ── printer_progress parsing ───────────────────────────────────────────────────


def test_printer_progress_parsing_not_printing() -> None:
    """printer_progress should report printing=False when not SD printing."""
    pytest.importorskip("fastmcp")

    response = b"CMD M27 Received.\r\nNot SD printing.\r\nok\n"
    mock_sock = _make_mock_socket(response)

    with patch("socket.create_connection", return_value=mock_sock):
        from jarvis_agent.modules.printer import printer_progress

        result = printer_progress()

    assert result["printing"] is False
    assert result["current_byte"] == 0
    assert result["total_bytes"] == 0


def test_printer_progress_parsing_printing() -> None:
    """printer_progress should parse SD byte progress correctly."""
    pytest.importorskip("fastmcp")

    response = b"CMD M27 Received.\r\nSD printing byte 12500/50000\r\nok\n"
    mock_sock = _make_mock_socket(response)

    with patch("socket.create_connection", return_value=mock_sock):
        from jarvis_agent.modules.printer import printer_progress

        result = printer_progress()

    assert result["printing"] is True
    assert result["current_byte"] == 12500
    assert result["total_bytes"] == 50000
    assert result["percent_complete"] == 25.0


# ── printer_temp parsing ───────────────────────────────────────────────────────


def test_printer_temp_parsing() -> None:
    """printer_temp should parse T0 and B temperature values."""
    pytest.importorskip("fastmcp")

    response = b"CMD M105 Received.\r\nT0:210 /210 B:60 /60\r\nok\n"
    mock_sock = _make_mock_socket(response)

    with patch("socket.create_connection", return_value=mock_sock):
        from jarvis_agent.modules.printer import printer_temp

        result = printer_temp()

    assert result["extruder_temp"] == 210.0
    assert result["extruder_target"] == 210.0
    assert result["bed_temp"] == 60.0
    assert result["bed_target"] == 60.0

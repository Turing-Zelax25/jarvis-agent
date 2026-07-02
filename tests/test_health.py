"""Tests for the Jarvis Agent health module."""
from __future__ import annotations

import sys

import pytest


def test_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """health() should return status='ok' with required keys."""
    # Monkeypatch importlib.metadata to avoid PackageNotFoundError in dev
    import importlib.metadata as meta

    class _MockMeta:
        @staticmethod
        def version(name: str) -> str:
            # Must be valid PEP 440 — fastmcp calls this internally too
            return "0.1.0"

    monkeypatch.setattr(meta, "version", _MockMeta.version, raising=True)

    # fastmcp must be available — skip if not installed
    pytest.importorskip("fastmcp")

    from jarvis_agent.modules.health import health

    result = health()

    assert result["status"] == "ok"
    assert "version" in result
    assert "platform" in result
    assert "python_version" in result
    assert "timestamp" in result


def test_health_timestamp_is_iso8601() -> None:
    """health() timestamp should parse as ISO 8601."""
    pytest.importorskip("fastmcp")

    from datetime import datetime
    from jarvis_agent.modules.health import health

    result = health()
    # Should not raise
    datetime.fromisoformat(result["timestamp"])


def test_health_python_version_matches() -> None:
    """health() python_version should match current interpreter."""
    pytest.importorskip("fastmcp")

    from jarvis_agent.modules.health import health

    result = health()
    assert sys.version in result["python_version"]

"""Tests for the Jarvis Agent browser module.

Uses unittest.mock to avoid needing a real Chrome instance / Playwright browser.
"""
from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Mock builders ─────────────────────────────────────────────────────────────


def _make_mock_page(
    url: str = "https://example.com",
    title: str = "Example",
    text: str = "Hello world",
    screenshot_bytes: bytes = b"\x89PNG",
    window_dims: dict[str, int] | None = None,
) -> AsyncMock:
    """Build a mock Playwright page."""
    page = AsyncMock()
    page.url = url
    page.title = AsyncMock(return_value=title)
    page.inner_text = AsyncMock(return_value=text)
    page.screenshot = AsyncMock(return_value=screenshot_bytes)
    page.goto = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.evaluate = AsyncMock(return_value=window_dims or {"w": 1280, "h": 720})
    page.close = AsyncMock()
    return page


def _make_mock_context(pages: list[AsyncMock]) -> MagicMock:
    ctx = MagicMock()
    ctx.pages = pages
    ctx.new_page = AsyncMock(return_value=pages[0] if pages else _make_mock_page())
    return ctx


def _make_mock_browser(page: AsyncMock) -> AsyncMock:
    """Build a mock Playwright browser with one context and one page."""
    context = _make_mock_context([page])
    browser = AsyncMock()
    browser.contexts = [context]
    browser.close = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    return browser


@asynccontextmanager
async def _mock_cdp_context(browser: AsyncMock):
    """async context manager that mimics async_playwright() / p.chromium.connect_over_cdp()."""
    pw = AsyncMock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    pw.chromium.launch = AsyncMock(return_value=browser)
    yield pw


def _patch_playwright(browser: AsyncMock):
    """Return a patch for async_playwright that yields our mock."""

    @asynccontextmanager
    async def _ctx_manager():
        yield browser.__aenter__.return_value if hasattr(browser, "__aenter__") else browser

    # async_playwright() is used as 'async with async_playwright() as p'
    # so we need a callable that returns an async context manager
    class _FakeAsyncPlaywright:
        async def __aenter__(self):
            pw = AsyncMock()
            pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
            pw.chromium.launch = AsyncMock(return_value=browser)
            return pw

        async def __aexit__(self, *_: Any) -> None:
            pass

    return patch(
        "jarvis_agent.modules.browser.async_playwright",
        return_value=_FakeAsyncPlaywright(),
    )


# ── browser_navigate ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_navigate_success() -> None:
    """browser_navigate returns navigated + current_url on success."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    page = _make_mock_page(url="https://example.com/page")
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_navigate

        result = await browser_navigate("https://example.com/page")

    assert result["status"] == "navigated"
    assert result["current_url"] == "https://example.com/page"
    page.goto.assert_awaited_once_with("https://example.com/page", timeout=30_000)
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_browser_navigate_fallback_when_playwright_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_navigate falls back to webbrowser.open() when Playwright unavailable."""
    pytest.importorskip("fastmcp")

    import jarvis_agent.modules.browser as bmod

    monkeypatch.setattr(bmod, "_PLAYWRIGHT_AVAILABLE", False)

    opened_urls: list[str] = []
    monkeypatch.setattr(bmod.webbrowser, "open", lambda u: opened_urls.append(u))

    result = await bmod.browser_navigate("https://fallback.test")

    assert result["status"] == "opened_fallback"
    assert result["current_url"] == "https://fallback.test"
    assert "https://fallback.test" in opened_urls


# ── browser_get_page_text ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_get_page_text_returns_title_and_text() -> None:
    """browser_get_page_text returns title, text, and text_length."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    long_text = "A" * 6000
    page = _make_mock_page(title="My Page", text=long_text)
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_get_page_text

        result = await browser_get_page_text()

    assert result["title"] == "My Page"
    assert len(result["text"]) == 5000  # truncated
    assert result["text_length"] == 6000


@pytest.mark.asyncio
async def test_browser_get_page_text_navigates_when_url_given() -> None:
    """browser_get_page_text calls page.goto when url param is supplied."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    page = _make_mock_page()
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_get_page_text

        await browser_get_page_text(url="https://navigate.test")

    page.goto.assert_awaited_once_with("https://navigate.test", timeout=30_000)


@pytest.mark.asyncio
async def test_browser_get_page_text_raises_when_playwright_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser_get_page_text raises ToolError when Playwright not installed."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    import jarvis_agent.modules.browser as bmod

    monkeypatch.setattr(bmod, "_PLAYWRIGHT_AVAILABLE", False)

    with pytest.raises(ToolError, match="Playwright is not installed"):
        await bmod.browser_get_page_text()


# ── browser_click ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_click_success() -> None:
    """browser_click calls page.click and returns clicked status."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    page = _make_mock_page()
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_click

        result = await browser_click("#submit-btn")

    assert result["status"] == "clicked"
    assert result["selector"] == "#submit-btn"
    page.click.assert_awaited_once_with("#submit-btn", timeout=10_000)


# ── browser_type ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_type_success() -> None:
    """browser_type calls page.fill and returns typed status."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    page = _make_mock_page()
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_type

        result = await browser_type("#username", "alice")

    assert result["status"] == "typed"
    assert result["selector"] == "#username"
    assert result["text"] == "alice"
    page.fill.assert_awaited_once_with("#username", "alice", timeout=10_000)


# ── browser_screenshot ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_screenshot_returns_base64_png() -> None:
    """browser_screenshot returns base64 PNG with width/height."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    raw_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    page = _make_mock_page(screenshot_bytes=raw_png, window_dims={"w": 1920, "h": 1080})
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_screenshot

        result = await browser_screenshot()

    assert result["format"] == "png"
    assert result["width"] == 1920
    assert result["height"] == 1080
    decoded = base64.b64decode(result["image_b64"])
    assert decoded == raw_png


# ── browser_launch (system-Chrome fallback path) ──────────────────────────────


@pytest.mark.asyncio
async def test_browser_launch_no_chrome_raises_when_playwright_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser_launch raises ToolError when neither Playwright nor system Chrome exists."""
    pytest.importorskip("fastmcp")

    from fastmcp.exceptions import ToolError
    import jarvis_agent.modules.browser as bmod

    monkeypatch.setattr(bmod, "_PLAYWRIGHT_AVAILABLE", False)

    with patch("subprocess.run", return_value=MagicMock(returncode=1)), \
         patch("os.path.isfile", return_value=False):
        with pytest.raises(ToolError, match="No Chrome/Chromium executable found"):
            await bmod.browser_launch()


@pytest.mark.asyncio
async def test_browser_launch_system_chrome_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """browser_launch uses system Chrome when Playwright is absent but chrome found."""
    pytest.importorskip("fastmcp")

    import jarvis_agent.modules.browser as bmod

    monkeypatch.setattr(bmod, "_PLAYWRIGHT_AVAILABLE", False)

    fake_proc = MagicMock()
    fake_proc.pid = 42

    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="/usr/bin/chromium\n")), \
         patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
        result = await bmod.browser_launch(port=9222, headless=True)

    assert result["status"] == "launched"
    assert result["pid"] == 42
    assert result["cdp_url"] == "http://localhost:9222"
    assert result["headless"] is True
    # Verify remote-debugging-port arg was passed
    popen_cmd = mock_popen.call_args[0][0]
    assert any("--remote-debugging-port=9222" in arg for arg in popen_cmd)
    assert any("--headless" in arg for arg in popen_cmd)


@pytest.mark.asyncio
async def test_browser_launch_playwright_path_detaches_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """browser_launch resolves the Playwright Chromium binary but starts it via
    subprocess.Popen (not p.chromium.launch inside the `async with` block), so
    the browser process survives after async_playwright() exits and remains
    reachable over CDP for subsequent tool calls.

    Regression test: an earlier implementation called
    `await p.chromium.launch(...)` inside `async with async_playwright() as p:`.
    Playwright kills every browser it spawned when that block exits, so the
    process was already dead by the time browser_navigate() tried to connect
    over CDP, even though browser_launch() had reported status="launched".
    """
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    import jarvis_agent.modules.browser as bmod

    fake_exe = "/fake/path/to/chrome"

    class _FakePlaywrightHandle:
        chromium = MagicMock(executable_path=fake_exe)

    class _FakeAsyncPlaywright:
        async def __aenter__(self):
            return _FakePlaywrightHandle()

        async def __aexit__(self, *_: Any) -> None:
            pass

    fake_proc = MagicMock()
    fake_proc.pid = 4242

    monkeypatch.setattr(bmod, "async_playwright", lambda: _FakeAsyncPlaywright())

    with patch("os.path.isfile", return_value=True), \
         patch("subprocess.Popen", return_value=fake_proc) as mock_popen:
        result = await bmod.browser_launch(port=9222, headless=True)

    assert result == {
        "status": "launched",
        "cdp_url": "http://localhost:9222",
        "pid": 4242,
        "headless": True,
    }
    # Launched via subprocess.Popen (detached), never via p.chromium.launch()
    popen_cmd = mock_popen.call_args[0][0]
    assert popen_cmd[0] == fake_exe
    assert mock_popen.call_args.kwargs.get("start_new_session") is True


# ── CDP disconnection error handling ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_browser_navigate_cdp_connection_error_raises_tool_error() -> None:
    """browser_navigate raises ToolError with helpful message on CDP connection failure."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    from fastmcp.exceptions import ToolError

    class _FakeAsyncPlaywright:
        async def __aenter__(self):
            pw = AsyncMock()
            pw.chromium.connect_over_cdp = AsyncMock(
                side_effect=Exception("net::ERR_CONNECTION_REFUSED")
            )
            return pw

        async def __aexit__(self, *_: Any) -> None:
            pass

    with patch(
        "jarvis_agent.modules.browser.async_playwright",
        return_value=_FakeAsyncPlaywright(),
    ):
        from jarvis_agent.modules.browser import browser_navigate

        with pytest.raises(ToolError, match="Chrome is not reachable"):
            await browser_navigate("https://example.com")


@pytest.mark.asyncio
async def test_browser_navigate_cdp_disconnect_error_raises_tool_error() -> None:
    """browser_navigate raises ToolError with disconnect message when browser closes."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("playwright")

    from fastmcp.exceptions import ToolError

    page = _make_mock_page()
    page.goto = AsyncMock(side_effect=Exception("Target closed"))
    browser = _make_mock_browser(page)

    with _patch_playwright(browser):
        from jarvis_agent.modules.browser import browser_navigate

        with pytest.raises(ToolError, match="disconnected"):
            await browser_navigate("https://example.com")

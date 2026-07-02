"""Browser automation tools for the Jarvis Agent MCP server.

Provides Chrome control via Playwright (CDP attach) or a simple webbrowser fallback.
Playwright is optional — install with: uv add 'jarvis-agent[browser]'
"""
from __future__ import annotations

import base64
import logging
import os
import webbrowser
from typing import Any

import fastmcp
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

browser_server = fastmcp.FastMCP("browser")

# Check if Playwright is installed (optional dependency)
try:
    import playwright  # type: ignore[import-untyped]  # noqa: F401
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False


def _require_playwright() -> None:
    """Raise a helpful ToolError if Playwright is not installed."""
    if not _PLAYWRIGHT_AVAILABLE:
        raise ToolError(
            "Playwright is not installed. "
            "Install it with: uv add 'jarvis-agent[browser]' && playwright install chromium"
        )


def _get_cdp_url() -> str:
    return os.environ.get("CHROME_CDP_URL", "http://localhost:9222")


# ── Tools ──────────────────────────────────────────────────────────────────────


@browser_server.tool()
async def browser_navigate(url: str) -> dict[str, str]:
    """Navigate the browser to a URL.

    Uses Playwright (CDP attach) if available; falls back to webbrowser.open().

    Args:
        url: URL to navigate to (must include scheme, e.g. https://).

    Returns:
        dict with 'status' and 'current_url' fields.
    """
    logger.info("Navigating to: %s", url)

    if _PLAYWRIGHT_AVAILABLE:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(_get_cdp_url())
            try:
                page = browser.contexts[0].pages[0] if browser.contexts else None
                if page is None:
                    context = await browser.new_context()
                    page = await context.new_page()
                await page.goto(url, timeout=30_000)
                current_url = page.url
            finally:
                await browser.close()
        return {"status": "navigated", "current_url": current_url}
    else:
        logger.warning("Playwright not available; falling back to webbrowser.open()")
        webbrowser.open(url)
        return {"status": "opened_fallback", "current_url": url}


@browser_server.tool()
async def browser_get_page_text(url: str | None = None) -> dict[str, Any]:
    """Get the text content of the current page (or navigate to url first).

    Args:
        url: Optional URL to navigate to before extracting text.

    Returns:
        dict with 'title', 'text' (first 5000 chars), and 'text_length' fields.
    """
    _require_playwright()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        try:
            page = browser.contexts[0].pages[0] if browser.contexts else None
            if page is None:
                context = await browser.new_context()
                page = await context.new_page()
            if url:
                await page.goto(url, timeout=30_000)
            title = await page.title()
            text = await page.inner_text("body")
        finally:
            await browser.close()

    return {
        "title": title,
        "text": text[:5000],
        "text_length": len(text),
    }


@browser_server.tool()
async def browser_click(selector: str) -> dict[str, str]:
    """Click an element by CSS selector.

    Args:
        selector: CSS selector for the element to click.

    Returns:
        dict with 'status' and 'selector' fields.
    """
    _require_playwright()
    logger.info("Clicking element: %s", selector)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        try:
            page = browser.contexts[0].pages[0]
            await page.click(selector, timeout=10_000)
        finally:
            await browser.close()

    return {"status": "clicked", "selector": selector}


@browser_server.tool()
async def browser_type(selector: str, text: str) -> dict[str, str]:
    """Type text into an element.

    Args:
        selector: CSS selector for the target input element.
        text: Text to type into the element.

    Returns:
        dict with 'status', 'selector', and 'text' fields.
    """
    _require_playwright()
    logger.info("Typing into: %s", selector)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        try:
            page = browser.contexts[0].pages[0]
            await page.fill(selector, text, timeout=10_000)
        finally:
            await browser.close()

    return {"status": "typed", "selector": selector, "text": text}


@browser_server.tool()
async def browser_screenshot() -> dict[str, Any]:
    """Take a screenshot of the current browser page.

    Returns:
        dict with 'image_b64' (base64 PNG), 'width', 'height', and 'format' fields.
    """
    _require_playwright()
    logger.info("Taking browser screenshot")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        try:
            page = browser.contexts[0].pages[0]
            buf = await page.screenshot(type="png")
            # Get dimensions via JS
            dims = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
        finally:
            await browser.close()

    return {
        "image_b64": base64.b64encode(buf).decode(),
        "width": dims.get("w", 0),
        "height": dims.get("h", 0),
        "format": "png",
    }

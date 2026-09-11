"""Browser automation tools for the Jarvis Agent MCP server.

Provides Chrome control via Playwright (CDP attach) or a simple webbrowser fallback.
Playwright is optional — install with: uv add 'jarvis-agent[browser]'

Chrome must be running with --remote-debugging-port=<port> for CDP tools to work.
Use browser_launch() to start a managed Chrome instance if one is not already running.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import webbrowser
from typing import Any

import fastmcp
from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

browser_server = fastmcp.FastMCP("browser")

# Check if Playwright is installed (optional dependency)
try:
    import playwright  # type: ignore[import-untyped]  # noqa: F401
    from playwright.async_api import (  # type: ignore[import-untyped]
        Browser,
        BrowserType,
        Error as PlaywrightError,
        async_playwright,
    )

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    async_playwright = None  # type: ignore[assignment,misc]
    PlaywrightError = Exception  # type: ignore[assignment,misc]
    Browser = None  # type: ignore[assignment,misc]
    BrowserType = None  # type: ignore[assignment,misc]


def _require_playwright() -> None:
    """Raise a helpful ToolError if Playwright is not installed."""
    if not _PLAYWRIGHT_AVAILABLE:
        raise ToolError(
            "Playwright is not installed. "
            "Install it with: uv add 'jarvis-agent[browser]' && playwright install chromium"
        )


def _get_cdp_url() -> str:
    return os.environ.get("CHROME_CDP_URL", "http://localhost:9222")


def _cdp_error(exc: Exception) -> ToolError:
    """Convert a Playwright CDP exception to a descriptive ToolError."""
    msg = str(exc)
    if "connect" in msg.lower() or "ECONNREFUSED" in msg or "net::ERR" in msg:
        return ToolError(
            f"Chrome is not reachable at {_get_cdp_url()}. "
            "Start Chrome with --remote-debugging-port=9222 or call browser_launch() first. "
            f"Original error: {exc}"
        )
    if "disconnected" in msg.lower() or "Target closed" in msg:
        return ToolError(
            f"Browser disconnected unexpectedly. "
            "The Chrome window may have been closed. "
            f"Original error: {exc}"
        )
    return ToolError(f"Browser error: {exc}")


# ── Tools ──────────────────────────────────────────────────────────────────────


@browser_server.tool()
async def browser_launch(
    port: int = 9222,
    headless: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Launch a Chromium browser instance with the CDP remote-debugging port open.

    If Playwright is installed, uses the Playwright-managed Chromium binary.
    Otherwise attempts to find a system Chrome/Chromium executable.

    Args:
        port: Remote-debugging port to open (default 9222).
              Also sets the CHROME_CDP_URL environment variable for subsequent calls.
        headless: Run in headless mode (default False — visible window on desktop).
        extra_args: Additional Chrome command-line flags (e.g. ["--start-maximized"]).

    Returns:
        dict with 'status', 'cdp_url', 'pid', and 'headless' fields.
    """
    cdp_url = f"http://localhost:{port}"
    os.environ["CHROME_CDP_URL"] = cdp_url

    chrome_bin: str | None = None

    if _PLAYWRIGHT_AVAILABLE:
        # Ask Playwright for the managed Chromium binary path, but launch it
        # ourselves via subprocess.Popen so the process is fully detached and
        # outlives this coroutine. Launching through `p.chromium.launch()`
        # inside an `async with async_playwright()` block ties the browser's
        # lifetime to the driver connection: when the `async with` exits at
        # the end of this function, Playwright terminates every browser it
        # spawned, so subsequent browser_navigate()/browser_screenshot() CDP
        # connects would fail with ECONNREFUSED even though this function
        # reported "status": "launched".
        try:
            async with async_playwright() as p:
                chrome_bin = p.chromium.executable_path
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not resolve Playwright Chromium path: %s", exc)
            chrome_bin = None

    if chrome_bin is None or not os.path.isfile(chrome_bin):
        # Fallback: find a system Chrome/Chromium binary
        candidates = [
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        chrome_bin = None
        for candidate in candidates:
            try:
                result = subprocess.run(
                    ["which", candidate], capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    chrome_bin = result.stdout.strip()
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                if os.path.isfile(candidate):
                    chrome_bin = candidate
                    break

    if chrome_bin is None:
        raise ToolError(
            "No Chrome/Chromium executable found. "
            "Install Playwright (uv add 'jarvis-agent[browser]' && playwright install chromium) "
            "or install Google Chrome."
        )

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        cmd.append("--headless=new")
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(
            "Launched Chrome: bin=%s cdp_url=%s pid=%d headless=%s",
            chrome_bin, cdp_url, proc.pid, headless,
        )
        return {
            "status": "launched",
            "cdp_url": cdp_url,
            "pid": proc.pid,
            "headless": headless,
        }
    except OSError as exc:
        raise ToolError(f"Failed to launch Chrome at {chrome_bin!r}: {exc}") from exc


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
            try:
                browser = await p.chromium.connect_over_cdp(_get_cdp_url())
            except Exception as exc:
                raise _cdp_error(exc) from exc
            try:
                page = browser.contexts[0].pages[0] if browser.contexts else None
                if page is None:
                    context = await browser.new_context()
                    page = await context.new_page()
                try:
                    await page.goto(url, timeout=30_000)
                    current_url = page.url
                except Exception as exc:
                    raise _cdp_error(exc) from exc
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
        try:
            browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        except Exception as exc:
            raise _cdp_error(exc) from exc
        try:
            page = browser.contexts[0].pages[0] if browser.contexts else None
            if page is None:
                context = await browser.new_context()
                page = await context.new_page()
            try:
                if url:
                    await page.goto(url, timeout=30_000)
                title = await page.title()
                text = await page.inner_text("body")
            except Exception as exc:
                raise _cdp_error(exc) from exc
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
        try:
            browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        except Exception as exc:
            raise _cdp_error(exc) from exc
        try:
            if not browser.contexts or not browser.contexts[0].pages:
                raise ToolError("No open pages in the connected browser.")
            page = browser.contexts[0].pages[0]
            try:
                await page.click(selector, timeout=10_000)
            except Exception as exc:
                raise _cdp_error(exc) from exc
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
        try:
            browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        except Exception as exc:
            raise _cdp_error(exc) from exc
        try:
            if not browser.contexts or not browser.contexts[0].pages:
                raise ToolError("No open pages in the connected browser.")
            page = browser.contexts[0].pages[0]
            try:
                await page.fill(selector, text, timeout=10_000)
            except Exception as exc:
                raise _cdp_error(exc) from exc
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
        try:
            browser = await p.chromium.connect_over_cdp(_get_cdp_url())
        except Exception as exc:
            raise _cdp_error(exc) from exc
        try:
            if not browser.contexts or not browser.contexts[0].pages:
                raise ToolError("No open pages in the connected browser.")
            page = browser.contexts[0].pages[0]
            try:
                buf = await page.screenshot(type="png")
                dims = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
            except Exception as exc:
                raise _cdp_error(exc) from exc
        finally:
            await browser.close()

    return {
        "image_b64": base64.b64encode(buf).decode(),
        "width": dims.get("w", 0),
        "height": dims.get("h", 0),
        "format": "png",
    }

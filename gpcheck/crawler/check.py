"""Validate that the crawler's GPC emulation reaches every layer a real GPC browser covers."""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from ..config import CONDITIONS, CrawlConfig
from ..fixtures.server import RESOLVER_ARG, FixtureServer
from .browser import launch, new_context


async def check_gpc(cfg: CrawlConfig) -> dict:
    """Returns, for GPC off and on, whether the signal was seen by: the navigation request,
    a subresource request, a cross-site iframe's request, and the iframe's navigator."""
    cfg.browser_args = list(dict.fromkeys([*cfg.browser_args, RESOLVER_ARG]))
    results = {}
    with FixtureServer() as server:
        async with async_playwright() as pw:
            browser = await launch(pw, cfg)
            for name in ("A", "B"):
                cond = CONDITIONS[name]
                ctx = await new_context(browser, cond, cfg)
                page = await ctx.new_page()
                await page.goto(server.url("echo.test"))
                await page.wait_for_function("window.__frame !== null", timeout=10_000)
                seen = await page.evaluate(
                    "() => ({navigation_header: window.__nav, subresource_header: window.__sub,"
                    " iframe_header: window.__frame.header, iframe_navigator: window.__frame.navigator,"
                    " page_navigator: navigator.globalPrivacyControl === true})")
                results["gpc_on" if cond.gpc else "gpc_off"] = seen
                await ctx.close()
            await browser.close()
    results["ok"] = all(results["gpc_on"].values()) and not any(results["gpc_off"].values())
    return results


def run_check(cfg: CrawlConfig) -> dict:
    return asyncio.run(check_gpc(cfg))

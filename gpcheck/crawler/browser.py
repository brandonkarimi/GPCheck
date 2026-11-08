"""Browser and context factory: the only place where GPC is switched on or off."""

from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Playwright

from ..config import Condition, CrawlConfig

# A GPC-enabled browser does two things: it sends `Sec-GPC: 1` on every request,
# and it exposes `navigator.globalPrivacyControl === true` to scripts. We reproduce both.
GPC_HEADER = {"Sec-GPC": "1"}
GPC_INIT_SCRIPT = """
(() => {
  try {
    Object.defineProperty(Navigator.prototype, 'globalPrivacyControl', {
      get: () => true, configurable: true, enumerable: true,
    });
  } catch (e) {}
})();
"""


async def launch(pw: Playwright, cfg: CrawlConfig) -> Browser:
    return await pw.chromium.launch(
        headless=not cfg.headful,
        executable_path=cfg.chromium_path,
        args=list(cfg.browser_args),
    )


def _user_agent(browser: Browser) -> str:
    # Headless Chromium advertises "HeadlessChrome", which many sites treat as a bot.
    major = browser.version.split(".")[0]
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )


async def new_context(browser: Browser, condition: Condition, cfg: CrawlConfig) -> BrowserContext:
    """A fresh, empty context (no cookies or storage carried over between visits)."""
    width, height = cfg.viewport
    context = await browser.new_context(
        user_agent=_user_agent(browser),
        locale=cfg.locale,
        timezone_id=cfg.timezone,
        viewport={"width": width, "height": height},
        extra_http_headers=dict(GPC_HEADER) if condition.gpc else None,
    )
    if condition.gpc:
        await context.add_init_script(GPC_INIT_SCRIPT)  # runs in every frame, before page scripts
    context.set_default_navigation_timeout(cfg.nav_timeout * 1000)
    return context

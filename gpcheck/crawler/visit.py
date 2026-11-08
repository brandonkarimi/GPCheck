"""One site visit under one condition: homepage + a few internal pages."""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from playwright.async_api import Browser, Page

from ..classify.domains import etld1, host_of
from ..config import Condition, CrawlConfig
from .banners import handle_banner
from .browser import new_context
from .collectors import Recorder, local_storage_keys, probe_signals, snapshot_cookies

SKIP_LINK = re.compile(r"(log-?in|log-?out|sign-?in|sign-?up|account|cart|checkout|subscribe|"
                       r"\.(pdf|zip|jpg|png|mp4|xml)$)", re.I)


def site_url(site: str) -> str:
    return site if "://" in site else f"https://{site.strip().strip('/')}/"


async def _dwell(page: Page, seconds: float) -> None:
    """Wait for the network to settle, then scroll slowly to trigger lazy-loaded trackers."""
    try:
        await page.wait_for_load_state("networkidle", timeout=min(10.0, max(seconds, 1.0)) * 1000)
    except Exception:
        pass
    steps = max(1, int(seconds // 2))
    for _ in range(steps):
        try:
            await page.mouse.wheel(0, 700)
        except Exception:
            pass
        await asyncio.sleep(seconds / steps)


async def discover_links(page: Page, home: str, n: int) -> list[str]:
    """Pick n same-site links. The choice is stable (hash-ordered) so runs are comparable."""
    if n <= 0:
        return []
    try:
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    except Exception:
        return []
    site = etld1(host_of(home))
    home_norm = urldefrag(home)[0].rstrip("/")
    seen: set[str] = set()
    for href in hrefs:
        url = urldefrag(href)[0]
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        if etld1(parts.hostname) != site or url.rstrip("/") == home_norm or SKIP_LINK.search(url):
            continue
        seen.add(url)
    ranked = sorted(seen, key=lambda u: hashlib.sha1(u.encode()).hexdigest())
    return ranked[:n]


async def visit_site(browser: Browser, site: str, condition: Condition, run: int, cfg: CrawlConfig,
                     subpages: list[str] | None = None) -> dict:
    home = site_url(site)
    record: dict = {
        "site": site, "url": home, "condition": condition.name, "gpc": condition.gpc,
        "banner_action": condition.banner, "run": run,
        "started": datetime.now(timezone.utc).isoformat(), "status": "ok", "error": None,
        "pages": [], "subpages": [], "requests": [], "cookies": [], "cookies_pre_action": None,
        "local_storage": [], "signals": {}, "banner": None, "browser": browser.version,
    }
    t0 = time.monotonic()
    context = await new_context(browser, condition, cfg)
    recorder = Recorder(context)
    try:
        page = await context.new_page()
        resp = await page.goto(home, wait_until="load")
        record["pages"].append({"url": page.url, "status": resp.status if resp else None})
        record["final_url"] = page.url

        if condition.banner:
            record["cookies_pre_action"] = await snapshot_cookies(context)
            record["banner"] = await handle_banner(page, condition.banner, cfg.banner_wait)
            recorder.phase = "post_action"

        await _dwell(page, cfg.dwell)
        record["signals"] = await probe_signals(page, recorder)
        record["local_storage"] = await local_storage_keys(page)
        if cfg.screenshots_dir:
            shot = Path(cfg.screenshots_dir) / f"{etld1(host_of(home))}_{condition.name}_{run}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(shot))

        # Use the same internal pages for every condition in a round (paired design).
        links = subpages if subpages is not None else await discover_links(page, page.url, cfg.subpages)
        record["subpages"] = links
        for url in links:
            recorder.page_index += 1
            try:
                resp = await page.goto(url, wait_until="load")
                record["pages"].append({"url": page.url, "status": resp.status if resp else None})
                await _dwell(page, cfg.dwell)
            except Exception as e:
                record["pages"].append({"url": url, "status": None, "error": f"{type(e).__name__}: {e}"[:300]})

        record["cookies"] = await snapshot_cookies(context)
    except Exception as e:
        record["status"] = "error"
        record["error"] = f"{type(e).__name__}: {e}"[:500]
        try:
            record["cookies"] = await snapshot_cookies(context)
        except Exception:
            pass
    finally:
        record["requests"] = recorder.requests
        record["duration"] = round(time.monotonic() - t0, 2)
        try:
            await context.close()
        except Exception:
            pass
    return record

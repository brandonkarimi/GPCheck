"""Collect each site's opt-out link and privacy policy text (one visit per site, GPC off)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from playwright.async_api import Browser, async_playwright

from ..classify.policy import classify_policy_text, pick_links
from ..config import CONDITIONS, CrawlConfig
from .browser import launch, new_context
from .visit import _goto, site_url

ANCHORS_JS = """els => els.map(e => ({text: (e.innerText || e.getAttribute('aria-label') || '').trim(),
                                      href: e.href || ''}))"""
MAX_POLICY_CHARS = 400_000


async def _settle(page, seconds: float) -> None:
    """Scroll to the bottom so lazily rendered footers appear."""
    for _ in range(3):
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        await asyncio.sleep(seconds / 3)


async def check_site(browser: Browser, site: str, cfg: CrawlConfig, settle: float = 6.0) -> dict:
    home = site_url(site)
    record: dict = {"site": site, "url": home, "checked": datetime.now(timezone.utc).isoformat(),
                    "status": "ok", "error": None, "pages": [], "title": None,
                    "opt_out_link": None, "policy_link": None, "policy_chars": 0,
                    "claim": "policy_not_found", "evidence": None, "mentions_california": False}
    context = await new_context(browser, CONDITIONS["A"], cfg)
    try:
        page = await context.new_page()
        resp = await _goto(page, home)
        record["pages"].append({"url": page.url, "status": resp.status if resp else None})
        await _settle(page, settle)
        record["title"] = (await page.title())[:200]
        anchors = await page.eval_on_selector_all("a, button", ANCHORS_JS)
        record.update(pick_links(anchors))
        if record["policy_link"]:
            resp = await _goto(page, record["policy_link"]["href"])
            record["pages"].append({"url": page.url, "status": resp.status if resp else None})
            try:  # policy pages are often rendered client-side
                await page.wait_for_load_state("networkidle", timeout=settle * 1000)
            except Exception:
                pass
            await _settle(page, settle / 2)
            text = (await page.inner_text("body"))[:MAX_POLICY_CHARS]
            record["policy_chars"] = len(text)
            record.update(classify_policy_text(text))
            if record["opt_out_link"] is None:  # some sites only link the opt-out from the policy
                more = pick_links(await page.eval_on_selector_all("a, button", ANCHORS_JS))
                record["opt_out_link_in_policy"] = more["opt_out_link"]
    except Exception as e:
        record["status"] = "error"
        record["error"] = f"{type(e).__name__}: {e}"[:500]
    finally:
        try:
            await context.close()
        except Exception:
            pass
    return record


async def check_policies(sites: list[str], cfg: CrawlConfig, out: str | Path,
                         log: Callable[[str], None] = print, settle: float = 6.0) -> Path:
    """Write one JSON line per site. Re-running resumes: sites already in the file are skipped."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(line)["site"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()}
    sem = asyncio.Semaphore(cfg.workers)
    lock = asyncio.Lock()
    async with async_playwright() as pw:
        browser = await launch(pw, cfg)

        async def one(site: str) -> None:
            async with sem:
                try:
                    rec = await asyncio.wait_for(check_site(browser, site, cfg, settle), cfg.visit_timeout)
                except asyncio.TimeoutError:
                    rec = {"site": site, "status": "error", "error": "visit timeout", "claim": "policy_not_found"}
                async with lock:
                    with out.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec) + "\n")
                log(f"{site}: {rec['status']}, opt-out link {'yes' if rec.get('opt_out_link') else 'no'}, "
                    f"policy: {rec.get('claim')}")

        await asyncio.gather(*(one(s) for s in sites if s not in done))
        await browser.close()
    return out

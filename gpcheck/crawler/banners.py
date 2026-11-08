"""Find a cookie banner and click 'Reject all' or 'Accept all'.

The selectors below cover the most common consent-management platforms (CMPs).
For a full study, swap in the Consent-O-Matic or DuckDuckGo autoconsent rule sets.
"""

from __future__ import annotations

import asyncio
import re
import time

from playwright.async_api import Frame, Page

# (cmp name, banner container, reject button, accept button)
CMP_RULES: list[tuple[str, str, str, str]] = [
    ("onetrust", "#onetrust-banner-sdk", "#onetrust-reject-all-handler", "#onetrust-accept-btn-handler"),
    ("cookiebot", "#CybotCookiebotDialog", "#CybotCookiebotDialogBodyButtonDecline",
     "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
    ("didomi", "#didomi-notice", "#didomi-notice-disagree-button", "#didomi-notice-agree-button"),
    ("trustarc", "#truste-consent-track", "#truste-consent-required", "#truste-consent-button"),
    ("quantcast", ".qc-cmp2-container", ".qc-cmp2-summary-buttons button[mode='secondary']",
     ".qc-cmp2-summary-buttons button[mode='primary']"),
    ("usercentrics", "#usercentrics-root", "[data-testid='uc-deny-all-button']", "[data-testid='uc-accept-all-button']"),
]

GENERIC_TEXT = {
    "reject": re.compile(r"^\s*(reject|decline|deny|refuse)( all)?( cookies)?\s*$|^\s*(only|strictly)? ?necessary( cookies)?( only)?\s*$", re.I),
    "accept": re.compile(r"^\s*(accept|allow|agree)( all)?( cookies)?\s*$|^\s*i agree\s*$|^\s*got it\s*$", re.I),
}


async def _visible(frame: Frame, selector: str) -> bool:
    try:
        loc = frame.locator(selector).first
        return await loc.count() > 0 and await loc.is_visible()
    except Exception:
        return False


async def _try_once(page: Page, action: str) -> dict | None:
    for frame in page.frames:
        for cmp, container, reject_sel, accept_sel in CMP_RULES:
            if not await _visible(frame, container):
                continue
            target = reject_sel if action == "reject" else accept_sel
            if await _visible(frame, target):
                await frame.locator(target).first.click(timeout=3000)
                return {"present": True, "cmp": cmp, "clicked": True, "first_layer": True, "method": "cmp_rule"}
            return {"present": True, "cmp": cmp, "clicked": False, "first_layer": False, "method": "cmp_rule"}
    for frame in page.frames:
        try:
            button = frame.get_by_role("button", name=GENERIC_TEXT[action]).first
            if await button.count() > 0 and await button.is_visible():
                await button.click(timeout=3000)
                return {"present": True, "cmp": "unknown", "clicked": True, "first_layer": True, "method": "text"}
        except Exception:
            continue
    return None


async def handle_banner(page: Page, action: str, wait: float) -> dict:
    deadline = time.monotonic() + wait
    while True:
        try:
            result = await _try_once(page, action)
        except Exception as e:
            result = {"present": True, "cmp": None, "clicked": False, "first_layer": None,
                      "method": "error", "error": str(e)[:200]}
        if result is not None or time.monotonic() >= deadline:
            break
        await asyncio.sleep(0.5)
    result = result or {"present": False, "cmp": None, "clicked": False, "first_layer": None, "method": None}
    result["action"] = action
    return result

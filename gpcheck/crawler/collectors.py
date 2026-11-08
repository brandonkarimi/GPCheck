"""Record network activity and read opt-out signals from a page."""

from __future__ import annotations

import time

from playwright.async_api import BrowserContext, Page, Request


class Recorder:
    """Logs every request made by a context, tagged with the page index and phase."""

    def __init__(self, context: BrowserContext):
        self.requests: list[dict] = []
        self.page_index = 0
        self.phase = "pre_action"   # becomes "post_action" after a banner click
        self.paused = False
        self._t0 = time.monotonic()
        context.on("request", self._on_request)

    def _on_request(self, request: Request) -> None:
        if self.paused:
            return
        try:
            frame_url = request.frame.url
        except Exception:  # service-worker requests have no frame
            frame_url = None
        headers = request.headers
        self.requests.append({
            "url": request.url,
            "method": request.method,
            "type": request.resource_type,
            "frame_url": frame_url,
            "navigation": request.is_navigation_request(),
            "sec_gpc": headers.get("sec-gpc"),
            "page_index": self.page_index,
            "phase": self.phase,
            "t": round(time.monotonic() - self._t0, 3),
        })


# Runs in the page. Every probe has a timeout so a broken CMP can't hang the crawl.
PROBE_JS = """
async () => {
  const timeout = (p, ms) => Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]);
  const clean = (v) => { try { return JSON.parse(JSON.stringify(v)); } catch (e) { return null; } };
  const out = {
    navigator_gpc: (typeof navigator.globalPrivacyControl === 'undefined') ? null : navigator.globalPrivacyControl,
    usp: null, gpp: null, gpc_json: null,
    has_uspapi: typeof window.__uspapi === 'function',
    has_gpp: typeof window.__gpp === 'function',
    has_tcfapi: typeof window.__tcfapi === 'function',
  };
  if (out.has_uspapi) {
    out.usp = await timeout(new Promise(r => {
      try { window.__uspapi('getUSPData', 1, (d, ok) => r(ok ? clean(d) : null)); } catch (e) { r(null); }
    }), 2000);
  }
  if (out.has_gpp) {
    out.gpp = await timeout(new Promise(r => {
      try {
        const v = window.__gpp('ping', (d) => r(clean(d)));
        if (v && typeof v === 'object' && v.gppVersion) r(clean(v));  // GPP 1.0 returns synchronously
      } catch (e) { r(null); }
    }), 2000);
  }
  try {
    const resp = await timeout(fetch('/.well-known/gpc.json', {credentials: 'omit', cache: 'no-store'}), 4000);
    if (resp && resp.ok) out.gpc_json = await resp.json().catch(() => null);
  } catch (e) {}
  return out;
}
"""


async def probe_signals(page: Page, recorder: Recorder) -> dict:
    recorder.paused = True  # our own gpc.json fetch is not site behavior
    try:
        return await page.evaluate(PROBE_JS)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:300]}
    finally:
        recorder.paused = False


async def snapshot_cookies(context: BrowserContext) -> list[dict]:
    return [
        {k: c.get(k) for k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")}
        for c in await context.cookies()
    ]


async def local_storage_keys(page: Page) -> list[str]:
    try:
        return await page.evaluate("() => Object.keys(window.localStorage)")
    except Exception:
        return []

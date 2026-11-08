"""Local ground-truth websites with known GPC behavior, for testing the whole pipeline.

All hosts end in `.test` and resolve to 127.0.0.1 via Chromium's --host-resolver-rules.

  honors.test      honors GPC: no tracker, USP '1YYN', publishes /.well-known/gpc.json
  ignores.test     ignores GPC: tracker always loads, USP '1YNN'
  liar.test        declares opt-out ('1YYN') when GPC is on but still loads the tracker
  clean.test       never tracks
  banner-ok.test   cookie banner; tracker loads only after 'Accept all'
  banner-bad.test  cookie banner; tracker loads no matter what you click
  echo.test        reports whether GPC reached the page, a subresource and a cross-site iframe
  tracker.test     the 'third-party tracker' (sets _fbp, sends a beacon)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RESOLVER_ARG = "--host-resolver-rules=MAP *.test 127.0.0.1"

USP_API = """
<script>
  window.__uspapi = function (cmd, ver, cb) {
    if (cmd === 'getUSPData') cb({version: 1, uspString: %s}, true);
  };
</script>"""

TRACKER_TAG = '<script src="http://tracker.test:{port}/pixel.js"></script>'
GPC = "navigator.globalPrivacyControl === true"

BANNER = """
<div id="onetrust-banner-sdk" style="position:fixed;bottom:0;left:0;right:0;background:#eee;padding:12px">
  We use cookies.
  <button id="onetrust-accept-btn-handler">Accept All Cookies</button>
  <button id="onetrust-reject-all-handler">Reject All</button>
</div>
<script>
  const consent = document.cookie.match(/consent=(\\w+)/);
  if (consent) document.getElementById('onetrust-banner-sdk').remove();
  function loadTracker() {
    const s = document.createElement('script'); s.src = 'http://tracker.test:{port}/pixel.js';
    document.head.appendChild(s);
  }
  function choose(v) {
    document.cookie = 'consent=' + v + '; path=/; max-age=31536000';
    document.getElementById('onetrust-banner-sdk')?.remove();
    if (v === 'accepted' || {always}) loadTracker();
  }
  document.getElementById('onetrust-accept-btn-handler')?.addEventListener('click', () => choose('accepted'));
  document.getElementById('onetrust-reject-all-handler')?.addEventListener('click', () => choose('rejected'));
  if ((consent && consent[1] === 'accepted') || {always}) loadTracker();
</script>"""


def page(title: str, body: str, port: int) -> str:
    links = "".join(f'<li><a href="/{p}">{p}</a></li>' for p in ("about", "products", "news"))
    return (f"<!doctype html><html><head><title>{title}</title></head><body>"
            f"<h1>{title}</h1><ul>{links}<li><a href=\"/login\">login</a></li></ul>"
            f"<div style=\"height:3000px\"></div>{body}</body></html>").replace("{port}", str(port))


def site_body(host: str, gpc_header: bool, port: int) -> str | None:
    if host == "honors.test":
        usp = USP_API % f"({GPC}) ? '1YYN' : '1YNN'"
        # Honors both mechanisms: server-side (header) and client-side (navigator property).
        tag = "" if gpc_header else (
            f"<script>if (!({GPC})) {{ const s = document.createElement('script');"
            f" s.src = 'http://tracker.test:{port}/pixel.js'; document.head.appendChild(s); }}</script>")
        return usp + tag
    if host == "ignores.test":
        return USP_API % "'1YNN'" + TRACKER_TAG
    if host == "liar.test":
        return USP_API % f"({GPC}) ? '1YYN' : '1YNN'" + TRACKER_TAG
    if host == "clean.test":
        return USP_API % f"({GPC}) ? '1YYN' : '1YNN'"
    if host == "banner-ok.test":
        return BANNER.replace("{always}", "false")
    if host == "banner-bad.test":
        return BANNER.replace("{always}", "true")
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "GPCheckFixture/1.0"

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, body: str | bytes, ctype: str = "text/html", status: int = 200, headers: dict | None = None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        host = (self.headers.get("Host") or "").split(":")[0]
        port = self.server.server_address[1]
        path = self.path.split("?")[0]
        gpc = self.headers.get("Sec-GPC") == "1"

        if host == "tracker.test":
            if path == "/pixel.js":
                js = ("document.cookie = '_fbp=fb.1.' + Date.now() + '.' + Math.random() + '; path=/; max-age=7776000';"
                      f"new Image().src = 'http://tracker.test:{port}/collect?ev=PageView&dl=' + encodeURIComponent(location.href);")
                return self._send(js, "application/javascript")
            if path == "/collect":
                return self._send(b"", "image/gif", 204)
            return self._send("not found", "text/plain", 404)

        if host == "echo.test":
            if path == "/sub.js":
                return self._send(f"window.__sub = {json.dumps(gpc)};", "application/javascript")
            body = (f"<script>window.__nav = {json.dumps(gpc)}; window.__frame = null;"
                    "window.addEventListener('message', e => { window.__frame = e.data; });</script>"
                    '<script src="/sub.js"></script>'
                    f'<iframe src="http://frame.test:{port}/frame"></iframe>')
            return self._send(f"<!doctype html><html><body>{body}</body></html>")
        if host == "frame.test":
            js = (f"parent.postMessage({{header: {json.dumps(gpc)}, "
                  "navigator: navigator.globalPrivacyControl === true}, '*');")
            return self._send(f"<!doctype html><script>{js}</script>")

        if path == "/.well-known/gpc.json":
            if host == "honors.test":
                return self._send(json.dumps({"gpc": True, "lastUpdate": "2026-01-01"}), "application/json")
            return self._send("not found", "text/plain", 404)

        body = site_body(host, gpc, port)
        if body is None:
            return self._send("unknown fixture host", "text/plain", 404)
        return self._send(page(f"{host} {path}", body, port))


class FixtureServer:
    def __init__(self, port: int = 0):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def url(self, host: str) -> str:
        return f"http://{host}:{self.port}/"

    def __enter__(self) -> "FixtureServer":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


EXPECTED_GPC = {
    "honors.test": "honors",
    "ignores.test": "ignores",
    "liar.test": "declares_only",
    "clean.test": "no_tracking_baseline",
}
EXPECTED_REJECT = {"banner-ok.test": "reject_works", "banner-bad.test": "reject_ignored"}

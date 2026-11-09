"""Download pinned copies of the public tracker / cookie / site lists."""

from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

SOURCES = {
    "ddg_tds.json": "https://staticcdn.duckduckgo.com/trackerblocking/v5/current/extension-tds.json",
    "disconnect_services.json": "https://raw.githubusercontent.com/disconnectme/disconnect-tracking-protection/master/services.json",
    "open_cookie_database.csv": "https://raw.githubusercontent.com/jkwakman/Open-Cookie-Database/master/open-cookie-database.csv",
}
TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"
USER_AGENT = "GPCheck research crawler (list download)"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_lists(dest: str | Path) -> list[Path]:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, url in SOURCES.items():
        path = dest / name
        path.write_bytes(_get(url))
        written.append(path)
    (dest / "VERSIONS.txt").write_text(
        f"Downloaded {date.today().isoformat()}\n" + "".join(f"{n}: {u}\n" for n, u in SOURCES.items()), encoding="utf-8")
    return written


def fetch_tranco(dest: str | Path, top: int) -> Path:
    data = _get(TRANCO_URL)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        text = zf.read(zf.namelist()[0]).decode()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "domain"])
        for i, row in enumerate(csv.reader(io.StringIO(text))):
            if i >= top:
                break
            w.writerow(row)
    return dest

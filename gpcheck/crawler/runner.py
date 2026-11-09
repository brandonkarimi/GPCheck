"""Schedule paired, order-randomized visits and write them to JSONL."""

from __future__ import annotations

import asyncio
import json
import random
import urllib.request
from pathlib import Path
from typing import Callable

from playwright.async_api import async_playwright

from ..config import Condition, CrawlConfig
from .browser import launch
from .visit import visit_site


def load_sites(path: str | Path) -> list[str]:
    """One site per line (domain or URL). CSV lines like 'rank,domain' are accepted too."""
    sites: list[str] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith(("rank,", "domain", "url")):
            continue
        sites.append(line.split(",")[-1].strip())
    return list(dict.fromkeys(sites))


def lookup_geo(timeout: float = 10.0) -> dict | None:
    """Best-effort location of this machine's public IP. Only city/region/country are kept;
    the IP address itself is never stored."""
    try:
        req = urllib.request.Request("https://ipinfo.io/json", headers={"User-Agent": "gpcheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        return {k: data.get(k) for k in ("city", "region", "country")}
    except Exception:
        return None


def _done(out: Path) -> set[tuple[str, str, int]]:
    if not out.exists():
        return set()
    done = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            done.add((r["site"], r["condition"], r["run"]))
        except (json.JSONDecodeError, KeyError):
            continue
    return done


async def crawl(sites: list[str], conditions: list[Condition], runs: int, cfg: CrawlConfig,
                out: str | Path, seed: int = 0, log: Callable[[str], None] = print,
                vantage: str = "unspecified", geo: dict | None = None) -> Path:
    """Each (site, run) visits all conditions back to back, in a random order, in fresh contexts.

    Re-running with the same output file resumes: finished visits are skipped.
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _done(out)
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(cfg.workers)

    async with async_playwright() as pw:
        browser = await launch(pw, cfg)

        async def site_round(site: str, run: int) -> None:
            order = list(conditions)
            random.Random(f"{seed}:{site}:{run}").shuffle(order)
            subpages: list[str] | None = None
            async with sem:
                for position, cond in enumerate(order):
                    if (site, cond.name, run) in done:
                        continue
                    try:
                        rec = await asyncio.wait_for(
                            visit_site(browser, site, cond, run, cfg, subpages), cfg.visit_timeout)
                    except asyncio.TimeoutError:
                        rec = {"site": site, "condition": cond.name, "gpc": cond.gpc, "run": run,
                               "banner_action": cond.banner, "status": "error",
                               "error": "visit timeout", "requests": [], "cookies": [], "signals": {}}
                    rec["order"] = position
                    rec["vantage"] = vantage
                    rec["geo"] = geo
                    if subpages is None and rec.get("status") == "ok":
                        subpages = rec.get("subpages", [])
                    async with lock:
                        with out.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(rec) + "\n")
                    log(f"[run {run}] {site} {cond.name}: {rec['status']} "
                        f"({len(rec.get('requests', []))} requests, {len(rec.get('cookies', []))} cookies)")

        for run in range(runs):
            await asyncio.gather(*(site_round(s, run) for s in sites))
        await browser.close()
    return out

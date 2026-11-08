"""Experimental conditions and crawl settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Condition:
    name: str
    gpc: bool
    banner: str | None  # None, "reject" or "accept"
    description: str


CONDITIONS: dict[str, Condition] = {
    "A": Condition("A", gpc=False, banner=None, description="Baseline: GPC off, no banner interaction"),
    "B": Condition("B", gpc=True, banner=None, description="GPC on, no banner interaction"),
    "C": Condition("C", gpc=False, banner="reject", description="GPC off, click 'Reject all'"),
    "D": Condition("D", gpc=True, banner="accept", description="GPC on, click 'Accept all' (conflict)"),
}


def parse_conditions(spec: str) -> list[Condition]:
    names = [s.strip().upper() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in CONDITIONS]
    if unknown:
        raise ValueError(f"unknown condition(s): {', '.join(unknown)}; choose from {', '.join(CONDITIONS)}")
    return [CONDITIONS[n] for n in names]


@dataclass
class CrawlConfig:
    dwell: float = 15.0            # seconds spent on each page (scrolling)
    subpages: int = 2              # same-site internal pages visited after the homepage
    nav_timeout: float = 30.0      # seconds per navigation
    visit_timeout: float = 240.0   # hard cap for a whole site visit
    banner_wait: float = 6.0       # seconds to look for a cookie banner
    workers: int = 4
    headful: bool = False
    chromium_path: str | None = field(default_factory=lambda: os.environ.get("GPCHECK_CHROMIUM") or None)
    browser_args: list[str] = field(default_factory=list)
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    viewport: tuple[int, int] = (1366, 768)
    screenshots_dir: str | None = None

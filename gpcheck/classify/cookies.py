"""Tracking-cookie classification: bundled seed names + optional Open Cookie Database CSV."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .domains import EntityMap, etld1
from .trackers import TrackerList

TRACKING_CATEGORIES = {"marketing", "analytics"}


@dataclass
class CookieDB:
    exact: set[str] = field(default_factory=set)
    prefixes: list[str] = field(default_factory=list)

    def name_is_tracking(self, name: str) -> bool:
        return name in self.exact or any(name.startswith(p) for p in self.prefixes)

    def add(self, name: str, wildcard: bool = False) -> None:
        name = name.strip()
        if not name:
            return
        if wildcard or name.endswith("*"):
            self.prefixes.append(name.rstrip("*"))
        else:
            self.exact.add(name)


def seed_cookie_db() -> CookieDB:
    db = CookieDB()
    text = resources.files("gpcheck.data").joinpath("seed_cookies.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            db.add(line)
    return db


def load_open_cookie_database(path: str | Path, db: CookieDB | None = None) -> CookieDB:
    """Open Cookie Database CSV (github.com/jkwakman/Open-Cookie-Database)."""
    db = db or CookieDB()
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("Category") or "").strip().lower() in TRACKING_CATEGORIES:
                db.add(row.get("Cookie / Data Key name", ""), wildcard=(row.get("Wildcard match") or "0").strip() == "1")
    return db


def is_tracking_cookie(cookie: dict, site_host: str, db: CookieDB, trackers: TrackerList,
                       entities: EntityMap) -> bool:
    """A cookie is tracking if its name is a known tracking cookie, or it belongs to a
    third-party tracker domain."""
    if db.name_is_tracking(cookie.get("name", "")):
        return True
    domain = (cookie.get("domain") or "").lstrip(".")
    return bool(domain) and entities.is_third_party(domain, site_host) and trackers.match(domain) is not None


def cookie_key(cookie: dict) -> str:
    return f"{etld1((cookie.get('domain') or '').lstrip('.'))}|{cookie.get('name')}"

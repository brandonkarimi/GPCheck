"""Tracker lists: bundled seed list, DuckDuckGo Tracker Radar (tds.json), Disconnect, plain text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .domains import EntityMap, etld1

DISCONNECT_CATEGORIES = {"Advertising", "Analytics", "Social", "FingerprintingInvasive", "FingerprintingGeneral",
                         "Cryptomining", "Email", "EmailAggressive"}


# The lists name the same company differently ("Google", "Google LLC", "Google Ads").
_LEGAL_SUFFIX = re.compile(r"[,\s]+(llc|inc|ltd|limited|gmbh|corp|corporation|co|s\.?a\.?s|s\.?a|b\.?v|ag|plc|"
                           r"pte|pty|s\.?r\.?l|a/s|ab|oy)\.?$", re.I)
_ALIASES = {
    "google ads": "Google", "alphabet": "Google", "youtube": "Google", "doubleclick": "Google",
    "facebook": "Meta", "meta platforms": "Meta", "instagram": "Meta",
    "yahoo!": "Yahoo", "verizon media": "Yahoo", "oath": "Yahoo",
    "amazon technologies": "Amazon", "amazon.com": "Amazon", "amazon web services": "Amazon",
    "microsoft corporation": "Microsoft", "xandr": "Microsoft", "appnexus": "Microsoft", "linkedin": "Microsoft",
    "adobe systems": "Adobe", "twitter": "X", "x corp": "X", "the trade desk": "The Trade Desk",
    "bytedance": "TikTok", "tiktok": "TikTok", "oracle corporation": "Oracle",
}


def canonical_owner(name: str) -> str:
    """One name per company: drop legal suffixes and fold known aliases together."""
    clean = name.strip()
    for _ in range(2):  # "Foo Technologies, Inc." and "Foo Co., Ltd."
        clean = _LEGAL_SUFFIX.sub("", clean).strip(" ,.")
    return _ALIASES.get(clean.lower(), clean)


@dataclass
class TrackerList:
    domains: dict[str, dict] = field(default_factory=dict)  # domain -> {"owner":..., "categories": [...]}
    entities: EntityMap = field(default_factory=EntityMap)
    sources: list[str] = field(default_factory=list)

    def match(self, host: str) -> dict | None:
        """Match a host or any of its parent domains."""
        labels = host.lower().strip(".").split(".")
        for i in range(len(labels) - 1):
            hit = self.domains.get(".".join(labels[i:]))
            if hit is not None:
                return hit
        return None

    def tracker_domain(self, host: str) -> str | None:
        return etld1(host) if self.match(host) is not None else None

    def owner(self, host: str) -> str:
        hit = self.match(host)
        if hit and hit.get("owner"):
            return canonical_owner(hit["owner"])
        return canonical_owner(self.entities.entity(host))

    def merge(self, other: "TrackerList") -> None:
        for d, info in other.domains.items():
            self.domains.setdefault(d, info)
        self.entities.update(other.entities)
        self.sources.extend(other.sources)


def _from_seed(data: dict, source: str) -> TrackerList:
    tl = TrackerList(sources=[source])
    entity_map = {}
    for owner, info in data["entities"].items():
        for d in info.get("domains", []):
            entity_map[d] = owner
        for d in info.get("trackers", []):
            tl.domains[d] = {"owner": owner, "categories": info.get("categories", [])}
    tl.entities = EntityMap(entity_map)
    return tl


def _from_tds(data: dict, source: str) -> TrackerList:
    """DuckDuckGo tracker data set (e.g. extension-tds.json)."""
    tl = TrackerList(sources=[source])
    for domain, info in data.get("trackers", {}).items():
        cats = [c for c in info.get("categories", [])]
        owner = (info.get("owner") or {}).get("name")
        if info.get("default") == "ignore" and not cats:
            continue
        tl.domains[domain.lower()] = {"owner": owner, "categories": cats}
    entity_map = {}
    for name, info in data.get("entities", {}).items():
        for d in info.get("domains", []):
            entity_map[d] = name
    tl.entities = EntityMap(entity_map)
    return tl


def _from_disconnect(data: dict, source: str) -> TrackerList:
    tl = TrackerList(sources=[source])
    entity_map = {}
    for category, services in data.get("categories", {}).items():
        for service in services:
            for name, sites in service.items():
                for _homepage, domains in sites.items():
                    if not isinstance(domains, list):
                        continue
                    for d in domains:
                        entity_map[d] = name
                        if category in DISCONNECT_CATEGORIES:
                            tl.domains.setdefault(d.lower(), {"owner": name, "categories": [category]})
    tl.entities = EntityMap(entity_map)
    return tl


def load_tracker_list(path: str | Path) -> TrackerList:
    path = Path(path)
    if path.suffix == ".txt":
        tl = TrackerList(sources=[str(path)])
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                tl.domains[line.lower()] = {"owner": None, "categories": []}
        return tl
    data = json.loads(path.read_text(encoding="utf-8"))
    if "trackers" in data and "entities" in data and isinstance(data["trackers"], dict):
        return _from_tds(data, str(path))
    if "categories" in data:
        return _from_disconnect(data, str(path))
    if "entities" in data:
        return _from_seed(data, str(path))
    raise ValueError(f"unrecognized tracker list format: {path}")


def seed_tracker_list() -> TrackerList:
    text = resources.files("gpcheck.data").joinpath("seed_trackers.json").read_text(encoding="utf-8")
    return _from_seed(json.loads(text), "seed_trackers.json")


def build_tracker_list(paths: list[str | Path] | None = None, include_seed: bool = True) -> TrackerList:
    tl = seed_tracker_list() if include_seed else TrackerList()
    for p in paths or []:
        tl.merge(load_tracker_list(p))
    return tl

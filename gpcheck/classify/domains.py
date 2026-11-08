"""Registrable domains (eTLD+1) and organization-level 'same party' checks."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit

import tldextract

# Use the Public Suffix List snapshot bundled with tldextract: no network, reproducible.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


@lru_cache(maxsize=100_000)
def etld1(host: str) -> str:
    host = host.lower().strip(".")
    if not host:
        return ""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    r = _extract(host)
    if r.domain and r.suffix:
        return f"{r.domain}.{r.suffix}"
    labels = host.split(".")  # unknown suffix (e.g. local *.test fixtures)
    return ".".join(labels[-2:])


class EntityMap:
    """Maps registrable domains to the organization that owns them."""

    def __init__(self, domain_to_entity: dict[str, str] | None = None):
        self.domain_to_entity = {d.lower(): e for d, e in (domain_to_entity or {}).items()}

    def entity(self, domain: str) -> str:
        d = etld1(domain)
        return self.domain_to_entity.get(d, d)

    def is_third_party(self, request_host: str, site_host: str) -> bool:
        return self.entity(request_host) != self.entity(site_host)

    def update(self, other: "EntityMap") -> None:
        self.domain_to_entity.update(other.domain_to_entity)

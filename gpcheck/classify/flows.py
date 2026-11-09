"""What a tracker request carries: privacy/opt-out parameters and event names.

Checks whether a site passes the user's opt-out down the ad-tech supply chain, or keeps
sending full tracking events to vendors.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

from .signals import parse_usp

USP_KEYS = ("us_privacy", "usp", "uspstring", "ccpa", "us_privacy_string")
GPP_KEYS = ("gpp", "gpp_string", "gppstring")
GPP_SID_KEYS = ("gpp_sid", "gppsid")
GPC_KEYS = ("gpc", "sec_gpc", "sec-gpc")
EVENT_KEYS = ("ev", "event", "en", "event_name", "eventname")

_KV = re.compile(r"(?:^|[?&;,\s\"'{])([A-Za-z_\-]{2,24})[\"']?\s*[:=]\s*[\"']?([^&;,\s\"'}]{0,200})")


def _flatten(obj, out: dict, depth: int = 0) -> None:
    if depth > 3:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _flatten(v, out, depth + 1)
            else:
                out.setdefault(str(k).lower(), str(v))
    elif isinstance(obj, list):
        for item in obj[:50]:
            _flatten(item, out, depth + 1)


def request_params(url: str, post_data: str | None = None) -> dict[str, str]:
    """Lower-cased parameter names -> first value, from the query string and the body
    (form-encoded, JSON, or key=value text)."""
    params = {k.lower(): v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}
    if post_data:
        body = post_data.strip()
        parsed = False
        if body[:1] in "{[":
            try:
                _flatten(json.loads(body), params)
                parsed = True
            except ValueError:
                pass
        if not parsed:
            for k, v in parse_qs(body, keep_blank_values=True).items():
                params.setdefault(k.lower(), v[0])
            for k, v in _KV.findall(body):
                params.setdefault(k.lower(), v)
    return params


def _first(params: dict, keys) -> str | None:
    for k in keys:
        if k in params and params[k] != "":
            return params[k]
    return None


def parse_flow(url: str, post_data: str | None = None) -> dict:
    p = request_params(url, post_data)
    usp = _first(p, USP_KEYS)
    usp_info = parse_usp(usp) if usp else None
    gpc = _first(p, GPC_KEYS)
    flags = {
        "us_privacy": usp,
        "usp_opted_out": bool(usp_info and usp_info.get("opted_out")),
        "gpp_present": _first(p, GPP_KEYS) is not None,
        "gpp_sid": _first(p, GPP_SID_KEYS),
        "gpc_param": gpc in ("1", "true", "True"),
        "google_npa": p.get("npa") == "1",          # non-personalized ads
        "google_ltd": p.get("ltd") == "1",          # limited ads
        "google_rdp": p.get("rdp") == "1",          # restricted data processing (CCPA)
        "meta_ldu": "ldu" in (p.get("dpo") or "").lower(),  # Meta Limited Data Use
        "event": _first(p, EVENT_KEYS),
    }
    flags["opt_out_passed"] = any(flags[k] for k in (
        "usp_opted_out", "gpc_param", "google_npa", "google_ltd", "google_rdp", "meta_ldu"))
    flags["privacy_signal_present"] = bool(usp or flags["gpp_present"] or flags["gpp_sid"] or gpc is not None
                                           or "npa" in p or "rdp" in p or "ltd" in p or "dpo" in p)
    return flags

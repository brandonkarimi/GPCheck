"""Decode a site's *declared* opt-out status: USP string, GPP, OneTrust cookie, gpc.json."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote


def parse_usp(usp: str | None) -> dict | None:
    """IAB US Privacy string, e.g. '1YYN': version, notice, opted-out-of-sale, LSPA."""
    if not usp or usp == "1---":  # absent, or CCPA does not apply
        return None
    if len(usp) != 4:
        return {"raw": usp, "opted_out": None}
    flag = {"Y": True, "N": False}.get(usp[2].upper())
    return {"raw": usp, "notice": usp[1], "opted_out": flag, "lspa": usp[3]}


US_SECTIONS = ("usnat", "usca", "usnatv1", "uscav1", "usco", "usct", "usva", "usut")


def parse_gpp(ping: dict | None) -> dict | None:
    """GPP ping data. In US sections, SaleOptOut / SharingOptOut / TargetedAdvertisingOptOut
    use 1 = opted out, 2 = did not opt out, 0 = not applicable."""
    if not ping:
        return None
    sections = ping.get("parsedSections") or {}
    result = {"gpp_string": ping.get("gppString"), "applicable": ping.get("applicableSections"),
              "sections": [], "opted_out": None, "gpc_flag": None}
    for name, data in sections.items():
        if name.lower() not in US_SECTIONS:
            continue
        if isinstance(data, list):  # some CMPs wrap the core segment in a list
            data = next((d for d in data if isinstance(d, dict)), {})
        if not isinstance(data, dict):
            continue
        result["sections"].append(name)
        values = [data.get(k) for k in ("SaleOptOut", "SharingOptOut", "TargetedAdvertisingOptOut")]
        if any(v == 1 for v in values):
            result["opted_out"] = True
        elif any(v == 2 for v in values) and result["opted_out"] is None:
            result["opted_out"] = False
        if "Gpc" in data:
            result["gpc_flag"] = bool(data["Gpc"])
    return result


def parse_optanon(value: str | None) -> dict | None:
    """OneTrust 'OptanonConsent' cookie. groups like 'C0001:1,C0004:0' (C0004 = targeting)."""
    if not value:
        return None
    q = parse_qs(unquote(value))
    groups = {}
    for item in (q.get("groups", [""])[0]).split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            groups[k] = v
    gpc = q.get("isGpcEnabled", [None])[0]
    return {"gpc_enabled": None if gpc is None else gpc == "1", "groups": groups,
            "targeting_off": groups.get("C0004") == "0" if "C0004" in groups else None}


def declared_signals(record: dict) -> dict:
    sig = record.get("signals") or {}
    cookies = {c.get("name"): c.get("value") for c in record.get("cookies", [])}
    usp_raw = (sig.get("usp") or {}).get("uspString") or cookies.get("usprivacy")
    usp = parse_usp(usp_raw)
    gpp = parse_gpp(sig.get("gpp"))
    optanon = parse_optanon(cookies.get("OptanonConsent"))
    gpc_json = sig.get("gpc_json")
    votes = [
        usp and usp.get("opted_out"),
        gpp and gpp.get("opted_out"),
        optanon and (optanon["gpc_enabled"] or optanon["targeting_off"]),
    ]
    known = [v for v in votes if v is not None]
    return {
        "usp": usp_raw, "usp_opted_out": usp and usp.get("opted_out"),
        "gpp_opted_out": gpp and gpp.get("opted_out"), "gpp_gpc_flag": gpp and gpp.get("gpc_flag"),
        "optanon_gpc": optanon and optanon["gpc_enabled"],
        "gpc_json_support": bool(isinstance(gpc_json, dict) and gpc_json.get("gpc") is True),
        "navigator_gpc": sig.get("navigator_gpc"),
        "declared_optout": (True if any(known) else False) if known else None,
        "has_signal_api": bool(sig.get("has_uspapi") or sig.get("has_gpp") or usp_raw or optanon),
    }

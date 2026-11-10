"""Turn raw visit records into per-visit metrics, per-site verdicts, and vendor statistics."""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from ..classify.cookies import CookieDB, cookie_key, is_tracking_cookie
from ..classify.domains import etld1, host_of
from ..classify.flows import parse_flow
from ..classify.signals import declared_signals
from ..classify.trackers import TrackerList

IGNORED_SCHEMES = ("data:", "blob:", "chrome-extension:", "about:")
# Requests that fetch code or assets rather than send data; excluded from opt-out propagation.
ASSET_TYPES = {"script", "stylesheet", "font", "media", "manifest"}

# A visit that reached a bot wall instead of the site says nothing about GPC, so it is excluded.
BLOCK_STATUS = {401, 403, 429, 503}
BLOCK_TITLE = re.compile(
    r"access( to this page has been)? denied|just a moment|attention required|pardon our interruption|"
    r"robot or human|are you a robot|verify (that )?you are (a )?human|security check|request blocked|"
    r"unusual traffic|captcha|bot or not", re.I)


def blocked_reason(rec: dict) -> str | None:
    """Why a visit that loaded without error still looks like a block page, or None."""
    pages = rec.get("pages") or []
    code = pages[0].get("status") if pages else None
    if code in BLOCK_STATUS:
        return f"blocked: homepage returned HTTP {code}"
    if BLOCK_TITLE.search(rec.get("title") or ""):
        return f"blocked: challenge page ({(rec.get('title') or '')[:60]!r})"
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval (95% by default) for a proportion k/n."""
    if not n:
        return None
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom)


def load_records(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class Classifier:
    trackers: TrackerList
    cookies: CookieDB

    def visit(self, rec: dict) -> dict:
        site_host = host_of(rec.get("final_url") or rec.get("url") or "")
        ent = self.trackers.entities
        banner = rec.get("banner") or {}
        after_click = bool(rec.get("banner_action") and banner.get("clicked"))
        tracker_domains: set[str] = set()
        first_page: set[str] = set()
        later_pages: set[str] = set()
        third_party: set[str] = set()
        vendors: set[str] = set()
        tracker_requests = 0
        with_optout = with_signal = data_requests = 0
        events: set[str] = set()
        gpc_marked = gpc_total = 0
        classified = []
        for r in rec.get("requests", []):
            url = r.get("url", "")
            if url.startswith(IGNORED_SCHEMES):
                continue
            host = host_of(url)
            if not host:
                continue
            gpc_total += 1
            gpc_marked += r.get("sec_gpc") == "1"
            is_3p = ent.is_third_party(host, site_host)
            is_tracker = is_3p and self.trackers.match(host) is not None
            counted = not (after_click and r.get("phase") != "post_action")
            data_request = is_tracker and r.get("type") not in ASSET_TYPES
            flow = parse_flow(url, r.get("post_data")) if data_request else None
            classified.append({**r, "host": host, "etld1": etld1(host), "third_party": is_3p,
                               "tracker": is_tracker, "counted": counted,
                               "vendor": self.trackers.owner(host) if is_tracker else None,
                               "opt_out_passed": flow["opt_out_passed"] if flow else None,
                               "event": flow["event"] if flow else None})
            if not counted:
                continue
            if is_3p:
                third_party.add(etld1(host))
            if is_tracker:
                d = etld1(host)
                tracker_domains.add(d)
                vendors.add(self.trackers.owner(host))
                tracker_requests += 1
                if flow:
                    data_requests += 1
                    with_optout += flow["opt_out_passed"]
                    with_signal += flow["privacy_signal_present"]
                    if flow["event"]:
                        events.add(flow["event"])
                (first_page if r.get("page_index", 0) == 0 else later_pages).add(d)

        def tracking_keys(cookies: list[dict] | None) -> set[str]:
            return {cookie_key(c) for c in cookies or []
                    if is_tracking_cookie(c, site_host, self.cookies, self.trackers, ent)}

        tracking_cookies = tracking_keys(rec.get("cookies"))
        new_after_click = tracking_cookies - tracking_keys(rec.get("cookies_pre_action")) if after_click else None
        declared = declared_signals(rec)
        status, error = rec.get("status"), rec.get("error")
        if status == "ok" and blocked_reason(rec):
            status, error = "blocked", blocked_reason(rec)
        return {
            "site": rec["site"], "condition": rec["condition"], "run": rec["run"], "gpc": rec.get("gpc"),
            "status": status, "error": error, "final_host": site_host,
            "n_requests": len(rec.get("requests", [])),
            "n_third_party": len(third_party),
            "n_trackers": len(tracker_domains),
            "n_tracker_requests": tracker_requests,
            "n_tracker_requests_with_optout": with_optout,
            "n_tracker_requests_with_privacy_signal": with_signal,
            "n_tracker_data_requests": data_requests,
            "optout_propagation_rate": round(with_optout / data_requests, 3) if data_requests else None,
            "tracker_events": ";".join(sorted(events)),
            "vantage": rec.get("vantage", "unspecified"),
            "n_trackers_first_page": len(first_page),
            "n_trackers_later_pages": len(later_pages),
            "n_tracking_cookies": len(tracking_cookies),
            "n_new_tracking_cookies_after_click": None if new_after_click is None else len(new_after_click),
            "gpc_header_rate": round(gpc_marked / gpc_total, 3) if gpc_total else None,
            "banner_present": banner.get("present"), "banner_cmp": banner.get("cmp"),
            "banner_clicked": banner.get("clicked"),
            **declared,
            "_trackers": sorted(tracker_domains), "_vendors": sorted(vendors),
            "_tracking_cookies": sorted(tracking_cookies), "_requests": classified,
        }


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _noise(values: list[float]) -> float:
    """Run-to-run variation under the *same* condition (the off-vs-off noise floor)."""
    if len(values) < 2:
        return 0.0
    return max(abs(a - b) for a, b in combinations(values, 2))


def _majority(values: list) -> bool | None:
    known = [v for v in values if v is not None]
    if not known:
        return None
    return sum(bool(v) for v in known) * 2 > len(known)


def _vendors_majority(visits: list[dict]) -> set[str]:
    counts = Counter(v for visit in visits for v in visit["_vendors"])
    return {v for v, n in counts.items() if n * 2 >= len(visits)}


def site_verdicts(visits: list[dict]) -> list[dict]:
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for v in visits:
        if v["status"] == "ok":
            by[(v["site"], v["condition"])].append(v)
    sites = sorted({v["site"] for v in visits})
    attempted = {(v["site"], v["condition"]) for v in visits}
    # A site that walls off some A/B visits often serves a degraded page on the others.
    blocked = {v["site"] for v in visits if v["status"] == "blocked" and v["condition"] in "AB"}
    rows = []
    for site in sites:
        a, b, c, d = (by.get((site, k), []) for k in "ABCD")
        row: dict = {"site": site, "runs_A": len(a), "runs_B": len(b)}
        for key, group in (("A", a), ("B", b), ("C", c), ("D", d)):
            row[f"trackers_{key}"] = _median([g["n_trackers"] for g in group])
            row[f"cookies_{key}"] = _median([g["n_tracking_cookies"] for g in group])
        noise_t = _noise([g["n_trackers"] for g in a])
        noise_c = _noise([g["n_tracking_cookies"] for g in a])
        row["noise_trackers"], row["noise_cookies"] = noise_t, noise_c
        row["declared_optout_B"] = _majority([g["declared_optout"] for g in b])
        row["declared_optout_A"] = _majority([g["declared_optout"] for g in a])
        row["gpc_json"] = any(g["gpc_json_support"] for g in a + b)
        row["gpc_header_rate_B"] = _median([g["gpc_header_rate"] for g in b if g["gpc_header_rate"] is not None])

        if (site, "A") not in attempted or (site, "B") not in attempted:
            row["verdict"] = None  # GPC pair not part of this crawl (e.g. banner-only run)
        elif not a or not b or site in blocked:
            row["verdict"] = "inconclusive"
        else:
            dt = row["trackers_A"] - row["trackers_B"]
            dc = row["cookies_A"] - row["cookies_B"]
            row["delta_trackers"], row["delta_cookies"] = dt, dc
            # Share of baseline tracker domains that still load with GPC on (1.0 = nothing changed).
            row["trackers_remaining"] = round(row["trackers_B"] / row["trackers_A"], 3) if row["trackers_A"] else None
            reduced = (dt >= 1 and dt > noise_t) or (dc >= 1 and dc > noise_c)
            declared = bool(row["declared_optout_B"])
            if row["trackers_A"] == 0 and row["cookies_A"] == 0:
                row["verdict"] = "no_tracking_baseline"
            elif reduced and declared:
                row["verdict"] = "honors"
            elif reduced:
                row["verdict"] = "reduces_without_declaring"
            elif declared:
                row["verdict"] = "declares_only"   # says it opted you out, keeps tracking
            else:
                row["verdict"] = "ignores"
            row["vendors_persisting"] = sorted(_vendors_majority(a) & _vendors_majority(b))
            row["vendors_dropped"] = sorted(_vendors_majority(a) - _vendors_majority(b))

        rates = [g["optout_propagation_rate"] for g in b if g["optout_propagation_rate"] is not None]
        rate_b = _median(rates)
        row["optout_propagation_B"] = rate_b
        if rate_b is None:
            row["propagation_verdict"] = None if not b else "no_tracker_data_requests"
        elif rate_b >= 0.999:
            row["propagation_verdict"] = "all_requests_carry_optout"
        elif rate_b > 0:
            row["propagation_verdict"] = "some_requests_carry_optout"
        else:
            row["propagation_verdict"] = "no_optout_passed"
        if c:
            clicked = _majority([g["banner_clicked"] for g in c])
            present = _majority([g["banner_present"] for g in c])
            row["banner_cmp"] = next((g["banner_cmp"] for g in c if g["banner_cmp"]), None)
            if not present:
                row["reject_verdict"] = "no_banner"
            elif not clicked:
                row["reject_verdict"] = "reject_not_found"
            elif a:
                after = _median([g["n_trackers"] for g in c])
                new_cookies = _median([g["n_new_tracking_cookies_after_click"] or 0 for g in c])
                drop = row["trackers_A"] - after
                stopped = after == 0 or (drop >= 1 and drop > noise_t)
                row["reject_verdict"] = "reject_works" if stopped and new_cookies == 0 else "reject_ignored"
        if d and b:
            if _majority([g["banner_clicked"] for g in d]):
                gap = row["trackers_D"] - row["trackers_B"]
                row["conflict_verdict"] = "accept_overrides_gpc" if gap >= 1 and gap > noise_t else "gpc_persists"
            else:
                row["conflict_verdict"] = "accept_not_found"
        rows.append(row)
    return rows


def vendor_persistence(site_rows: list[dict], visits: list[dict]) -> list[dict]:
    """For each vendor: on how many sites it loads with GPC off, and how often it still loads with GPC on."""
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for v in visits:
        if v["status"] == "ok":
            by[(v["site"], v["condition"])].append(v)
    off_sites: Counter = Counter()
    still_on: Counter = Counter()
    for row in site_rows:
        a, b = by.get((row["site"], "A"), []), by.get((row["site"], "B"), [])
        if not a or not b:
            continue
        va, vb = _vendors_majority(a), _vendors_majority(b)
        for vendor in va:
            off_sites[vendor] += 1
            still_on[vendor] += vendor in vb
    return sorted(({"vendor": v, "sites_gpc_off": n, "sites_still_with_gpc_on": still_on[v],
                    "persistence_rate": round(still_on[v] / n, 3)} for v, n in off_sites.items()),
                  key=lambda r: (-r["sites_gpc_off"], r["vendor"]))


def paired_stats(site_rows: list[dict]) -> dict:
    from scipy.stats import binomtest, wilcoxon

    pairs = [r for r in site_rows if r.get("verdict") not in (None, "inconclusive")]
    out: dict = {"n_sites_paired": len(pairs)}
    for metric in ("trackers", "cookies"):
        off = [r[f"{metric}_A"] for r in pairs]
        on = [r[f"{metric}_B"] for r in pairs]
        out[f"mean_{metric}_gpc_off"] = round(statistics.fmean(off), 3) if off else None
        out[f"mean_{metric}_gpc_on"] = round(statistics.fmean(on), 3) if on else None
        diffs = [x - y for x, y in zip(off, on) if x != y]
        if len(diffs) >= 6:
            res = wilcoxon(off, on, zero_method="wilcox", alternative="greater")
            out[f"wilcoxon_{metric}_p"] = float(res.pvalue)
        else:
            out[f"wilcoxon_{metric}_p"] = None
    # McNemar (exact): does "any tracker loads" flip from yes to no when GPC is on?
    b = sum(1 for r in pairs if r["trackers_A"] > 0 and r["trackers_B"] == 0)
    c = sum(1 for r in pairs if r["trackers_A"] == 0 and r["trackers_B"] > 0)
    out["mcnemar_off_yes_on_no"], out["mcnemar_off_no_on_yes"] = b, c
    out["mcnemar_p"] = float(binomtest(b, b + c, 0.5).pvalue) if b + c else None
    return out


def vendor_propagation(visits: list[dict]) -> list[dict]:
    """Per vendor, with GPC on (condition B): how many tracker requests carried an opt-out."""
    total: Counter = Counter()
    passed: Counter = Counter()
    sites: dict[str, set] = defaultdict(set)
    for v in visits:
        if v["status"] != "ok" or v["condition"] != "B":
            continue
        for r in v["_requests"]:
            if r["tracker"] and r["counted"] and r["opt_out_passed"] is not None:
                total[r["vendor"]] += 1
                passed[r["vendor"]] += bool(r["opt_out_passed"])
                sites[r["vendor"]].add(v["site"])
    return sorted(({"vendor": k, "sites": len(sites[k]), "requests_gpc_on": n,
                    "requests_with_optout": passed[k], "share_with_optout": round(passed[k] / n, 3)}
                   for k, n in total.items()), key=lambda r: (-r["sites"], r["vendor"]))


def vantage_comparison(rows_by_vantage: dict[str, list[dict]]) -> list[dict]:
    """One row per site with its GPC verdict at each vantage point (e.g. state)."""
    vantages = sorted(rows_by_vantage)
    table: dict[str, dict] = defaultdict(dict)
    for vantage, rows in rows_by_vantage.items():
        for r in rows:
            if r.get("verdict") is not None:
                table[r["site"]][vantage] = r["verdict"]
    out = []
    for site, verdicts in sorted(table.items()):
        row = {"site": site, **{v: verdicts.get(v) for v in vantages}}
        honored = {v for v in vantages if verdicts.get(v) == "honors"}
        row["honors_only_some"] = bool(honored) and len(honored) < len([v for v in vantages if verdicts.get(v)])
        out.append(row)
    return out

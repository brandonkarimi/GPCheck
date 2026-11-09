"""Write analysis outputs: CSV tables, a DuckDB database, and a Markdown report."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..classify.domains import etld1, host_of
from ..classify.policy import CLAIM_TEXT, says_vs_does
from .metrics import (Classifier, blocked_reason, cohen_kappa, load_records, paired_stats, site_verdicts, vantage_comparison,
                      vendor_persistence, vendor_propagation, wilson)

VERDICT_TEXT = {
    "honors": "Declares an opt-out and tracking drops",
    "reduces_without_declaring": "Tracking drops, but no opt-out flag is set",
    "declares_only": "Declares an opt-out but keeps tracking (says vs. does gap)",
    "ignores": "No declared opt-out and no change in tracking",
    "no_tracking_baseline": "No trackers even with GPC off (nothing to stop)",
    "inconclusive": "Missing, failed or blocked visits",
}


PRIMARY_VANTAGE = "CA"


def site_key(site: str) -> str:
    """Registrable domain, so 'https://www.cnn.com/' and 'cnn.com' match."""
    host = host_of(site if "://" in site else f"https://{site}/")
    return (etld1(host) or host or site).lower()


def load_site_column(path: str | Path, column: str) -> dict[str, str]:
    """Read a CSV with a `site` column and return {site key: value of `column`}, skipping blanks."""
    with open(path, newline="", encoding="utf-8") as fh:
        return {site_key(row["site"]): row[column].strip() for row in csv.DictReader(fh)
                if (row.get("site") or "").strip() and (row.get(column) or "").strip()}


def write_sample(sites_csv: str | Path, dest: str | Path, n: int, seed: int = 0) -> list[str]:
    """Draw a seeded random sample of sites with a verdict, for blind manual checking.

    The automated verdict is deliberately left out of the sheet."""
    with open(sites_csv, newline="", encoding="utf-8") as fh:
        eligible = sorted({row["site"] for row in csv.DictReader(fh)
                           if row.get("verdict") and row["verdict"] != "inconclusive"})
    chosen = sorted(random.Random(seed).sample(eligible, min(n, len(eligible))))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["site", "manual_verdict", "notes"])
        writer.writerows([site, "", ""] for site in chosen)
    return chosen


def manual_agreement(sites: list[dict], manual: dict[str, str]) -> dict:
    """Compare automated verdicts with hand-assigned ones."""
    pairs = [(s["site"], s["verdict"], manual[site_key(s["site"])]) for s in sites
             if s.get("verdict") and site_key(s["site"]) in manual]
    agree = sum(auto == hand for _, auto, hand in pairs)
    kappa = cohen_kappa([(auto, hand) for _, auto, hand in pairs])
    return {"n": len(pairs), "agree": agree, "kappa": None if kappa is None else round(kappa, 3),
            "disagreements": [{"site": site, "automated": auto, "manual": hand}
                              for site, auto, hand in pairs if auto != hand]}


SAYS_VS_DOES_TEXT = {
    "claims_but_does_not_honor": "Policy says GPC is honored, but tracking did not drop (says vs. does gap)",
    "claim_matches_behavior": "Policy says GPC is honored, and tracking dropped",
    "no_claim_and_does_not_honor": "No commitment to GPC in the policy, and tracking did not drop",
    "honors_without_claiming": "Tracking dropped, though the policy makes no commitment",
}


def policy_by_site(records: list[dict]) -> dict[str, dict]:
    """Index `gpcheck policy` records by site, discarding visits that failed or hit a bot wall."""
    out = {}
    for r in records:
        readable = r.get("status") == "ok" and not blocked_reason(r)
        link = (r.get("opt_out_link") or r.get("opt_out_link_in_policy")) if readable else None
        out[site_key(r["site"])] = {
            "policy_readable": readable,
            "opt_out_link": bool(link) if readable else None,
            "opt_out_link_text": link["text"] if link else None,
            "policy_claim": r.get("claim") if readable else None,
            "policy_evidence": r.get("evidence") if readable else None,
            "policy_url": (r.get("policy_link") or {}).get("href") if readable else None,
        }
    return out


def analyze(input_paths, out_dir: str | Path, classifier: Classifier,
            categories: dict[str, str] | None = None, manual: dict[str, str] | None = None,
            policy: list[dict] | None = None) -> dict:
    """Analyze one or more crawl files (e.g. one per state) together."""
    if isinstance(input_paths, (str, Path)):
        input_paths = [input_paths]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = [r for p in input_paths for r in load_records(p)]
    visits = [classifier.visit(r) for r in records]

    by_vantage: dict[str, list[dict]] = {}
    for v in visits:
        by_vantage.setdefault(v["vantage"], []).append(v)
    rows_by_vantage = {k: site_verdicts(vs) for k, vs in by_vantage.items()}
    policies = policy_by_site(policy) if policy else None
    for k, rows in rows_by_vantage.items():
        for r in rows:
            r["vantage"] = k
            if categories is not None:
                r["category"] = categories.get(site_key(r["site"]), "uncategorized")
            if policies and site_key(r["site"]) in policies:
                r.update(policies[site_key(r["site"])])
                r["says_vs_does"] = says_vs_does(r["policy_claim"], r.get("verdict"))
    primary = PRIMARY_VANTAGE if PRIMARY_VANTAGE in by_vantage else sorted(by_vantage)[0] if by_vantage else None
    sites = rows_by_vantage.get(primary, [])
    primary_visits = by_vantage.get(primary, [])
    vendors = vendor_persistence(sites, primary_visits)
    propagation = vendor_propagation(primary_visits)
    stats = {k: paired_stats(rows) for k, rows in rows_by_vantage.items()}
    comparison = vantage_comparison(rows_by_vantage) if len(by_vantage) > 1 else []
    validation = manual_agreement(sites, manual) if manual else None

    all_rows = [r for rows in rows_by_vantage.values() for r in rows]
    visits_df = pd.DataFrame([{k: v for k, v in x.items() if not k.startswith("_")} |
                              {"trackers": ";".join(x["_trackers"]), "vendors": ";".join(x["_vendors"])}
                              for x in visits])
    sites_df = pd.DataFrame([{k: (";".join(v) if isinstance(v, list) else v) for k, v in s.items()} for s in all_rows])
    vendors_df = pd.DataFrame(vendors, columns=["vendor", "sites_gpc_off", "sites_still_with_gpc_on", "persistence_rate"])
    propagation_df = pd.DataFrame(propagation, columns=["vendor", "sites", "requests_gpc_on",
                                                        "requests_with_optout", "share_with_optout"])
    comparison_df = pd.DataFrame(comparison)
    requests_df = pd.DataFrame([{"site": x["site"], "vantage": x["vantage"], "condition": x["condition"], "run": x["run"],
                                 **{k: r.get(k) for k in ("url", "host", "etld1", "type", "page_index", "phase",
                                                          "sec_gpc", "third_party", "tracker", "counted", "vendor",
                                                          "opt_out_passed", "event")}}
                                for x in visits for r in x["_requests"]])
    tables = {"visits": visits_df, "sites": sites_df, "vendors": vendors_df,
              "propagation": propagation_df, "vantage_comparison": comparison_df, "requests": requests_df}
    for name in ("visits", "sites", "vendors", "propagation", "vantage_comparison"):
        if not tables[name].empty:
            tables[name].to_csv(out / f"{name}.csv", index=False)
    (out / "stats.json").write_text(json.dumps(stats | ({"manual_validation": validation} if validation else {}),
                                               indent=2), encoding="utf-8")

    import duckdb
    db_path = out / "gpcheck.duckdb"
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    for name, df in tables.items():
        if not df.empty:
            con.register("df_tmp", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM df_tmp")
            con.unregister("df_tmp")
    con.close()

    report = render_report(sites, vendors, stats.get(primary, paired_stats([])), primary_visits, classifier,
                           ", ".join(str(p) for p in input_paths), primary=primary,
                           propagation=propagation, comparison=comparison, vantages=sorted(by_vantage),
                           all_stats=stats, validation=validation)
    (out / "report.md").write_text(report, encoding="utf-8")
    return {"sites": sites, "all_sites": all_rows, "vendors": vendors, "propagation": propagation,
            "comparison": comparison, "stats": stats, "validation": validation, "out_dir": str(out)}


def _fmt_p(p: float | None) -> str:
    return "n/a (too few differing pairs)" if p is None else f"{p:.4g}"


PROPAGATION_TEXT = {
    "all_requests_carry_optout": "Every tracker request carries an opt-out signal",
    "some_requests_carry_optout": "Some tracker requests carry an opt-out signal",
    "no_optout_passed": "Trackers load with no opt-out signal attached",
    "no_tracker_data_requests": "No data-sending tracker requests with GPC on",
}


def render_report(sites, vendors, stats, visits, classifier, input_path, primary=None, propagation=(),
                  comparison=(), vantages=(), all_stats=None, validation=None) -> str:
    gpc_sites = [s for s in sites if s["verdict"] is not None]
    verdicts = Counter(s["verdict"] for s in gpc_sites)
    total = len(gpc_sites)
    lines = [
        "# GPCheck results", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from `{input_path}`. "
        f"Tracker sources: {', '.join(classifier.trackers.sources)}.", "",
        f"Vantage points: {', '.join(vantages) or 'n/a'}. Sections below use **{primary}** unless noted.", "",
        f"**{len(sites)} sites, {len(visits)} visits** ({sum(v['status'] == 'error' for v in visits)} failed, "
        f"{sum(v['status'] == 'blocked' for v in visits)} blocked by bot protection).", "",
        "## GPC verdicts (condition A: GPC off vs. B: GPC on)", "",
        "| Verdict | Sites | Share | 95% CI | Meaning |", "|---|---:|---:|---:|---|",
    ]
    for key, text in VERDICT_TEXT.items():
        n = verdicts.get(key, 0)
        ci = wilson(n, total)
        lines.append(f"| `{key}` | {n} | {n / total:.0%} | {ci[0]:.0%}–{ci[1]:.0%} | {text} |" if total
                     else f"| `{key}` | 0 | – | – | {text} |")
    lines += ["", "Intervals are Wilson score intervals over all sites with an A/B pair."]
    blocked_sites = sorted({v["site"] for v in visits if v["status"] == "blocked"})
    if blocked_sites:
        lines += ["", f"Sites with at least one blocked visit: {', '.join(blocked_sites)}"]
    if any("category" in s for s in gpc_sites):
        keys = [k for k in VERDICT_TEXT if verdicts.get(k)]
        lines += ["", "## GPC verdicts by site category", "",
                  "| Category | Sites | " + " | ".join(f"`{k}`" for k in keys) + " |",
                  "|---|---:|" + "---:|" * len(keys)]
        for cat in sorted({s.get("category", "uncategorized") for s in gpc_sites}):
            vc = Counter(s["verdict"] for s in gpc_sites if s.get("category", "uncategorized") == cat)
            lines.append(f"| {cat} | {sum(vc.values())} | " + " | ".join(str(vc.get(k, 0)) for k in keys) + " |")
    with_policy = [s for s in gpc_sites if s.get("policy_claim")]
    if any("policy_readable" in s for s in gpc_sites):
        unread = sum(1 for s in gpc_sites if s.get("policy_readable") is False)
        lines += ["", "## Privacy policy claims vs. measured behavior", "",
                  f"Policy check covered {sum('policy_readable' in s for s in gpc_sites)} sites; "
                  f"{unread} could not be read (failed or blocked).", "",
                  "| What the policy says about GPC | Sites | Has an opt-out link |", "|---|---:|---:|"]
        claims = Counter(s["policy_claim"] for s in with_policy)
        for key, text in CLAIM_TEXT.items():
            linked = sum(1 for s in with_policy if s["policy_claim"] == key and s.get("opt_out_link"))
            lines.append(f"| {text} | {claims.get(key, 0)} | {linked} |")
        gaps = Counter(s["says_vs_does"] for s in with_policy if s.get("says_vs_does"))
        lines += ["", "| Says vs. does | Sites | Meaning |", "|---|---:|---|"]
        lines += [f"| `{k}` | {gaps.get(k, 0)} | {text} |" for k, text in SAYS_VS_DOES_TEXT.items()]
        no_route = [s["site"] for s in with_policy if s.get("opt_out_link") is False
                    and s.get("verdict") in ("ignores", "declares_only")]
        lines += ["", f"Sites that neither reduce tracking under GPC nor show an opt-out link: **{len(no_route)}**"
                  + (f" ({', '.join(no_route[:15])})" if no_route else "")]
        claimed = [s for s in with_policy if s.get("says_vs_does") == "claims_but_does_not_honor"]
        if claimed:
            lines += ["", "Sites whose policy claims to honor GPC while tracking did not drop:", ""]
            lines += [f"- **{s['site']}** (`{s['verdict']}`): \"{s['policy_evidence']}\"" for s in claimed]
    if validation:
        lines += ["", "## Manual validation", ""]
        if validation["n"]:
            ci = wilson(validation["agree"], validation["n"])
            lines.append(f"Automated and manual verdicts agree on **{validation['agree']} of {validation['n']}** "
                         f"hand-checked sites ({validation['agree'] / validation['n']:.0%}, 95% CI "
                         f"{ci[0]:.0%}–{ci[1]:.0%}); Cohen's kappa = {validation['kappa']}.")
            if validation["disagreements"]:
                lines += ["", "| Site | Automated | Manual |", "|---|---|---|"]
                lines += [f"| {d['site']} | `{d['automated']}` | `{d['manual']}` |" for d in validation["disagreements"]]
        else:
            lines.append("No hand-checked site matches a site with an automated verdict.")
    lines += [
        "", "## Paired statistics", "",
        f"- Sites with paired data: {stats['n_sites_paired']}",
        f"- Mean tracker domains: GPC off {stats['mean_trackers_gpc_off']} → GPC on {stats['mean_trackers_gpc_on']}"
        f" (Wilcoxon one-sided p = {_fmt_p(stats['wilcoxon_trackers_p'])})",
        f"- Mean tracking cookies: GPC off {stats['mean_cookies_gpc_off']} → GPC on {stats['mean_cookies_gpc_on']}"
        f" (Wilcoxon one-sided p = {_fmt_p(stats['wilcoxon_cookies_p'])})",
        f"- Sites where all trackers disappear with GPC: {stats['mcnemar_off_yes_on_no']}; "
        f"sites where trackers appear only with GPC: {stats['mcnemar_off_no_on_yes']} "
        f"(exact McNemar p = {_fmt_p(stats['mcnemar_p'])})",
    ]
    header_rates = [s["gpc_header_rate_B"] for s in sites if s.get("gpc_header_rate_B") is not None]
    if header_rates:
        lines.append(f"- GPC sanity check: median share of condition-B requests carrying `Sec-GPC: 1` = "
                     f"{sorted(header_rates)[len(header_rates) // 2]:.0%}")
    lines += ["", "## Vendors that keep loading with GPC on", "",
              "| Vendor | Sites (GPC off) | Still loads with GPC on | Persistence |", "|---|---:|---:|---:|"]
    for v in vendors[:20]:
        lines.append(f"| {v['vendor']} | {v['sites_gpc_off']} | {v['sites_still_with_gpc_on']} | {v['persistence_rate']:.0%} |")
    prop = Counter(s.get("propagation_verdict") for s in gpc_sites if s.get("propagation_verdict"))
    if prop:
        lines += ["", "## Is the opt-out passed to vendors? (GPC on)", "",
                  "| Result | Sites | Meaning |", "|---|---:|---|"]
        for key, text in PROPAGATION_TEXT.items():
            lines.append(f"| `{key}` | {prop.get(key, 0)} | {text} |")
    if propagation:
        lines += ["", "| Vendor | Sites | Requests (GPC on) | With opt-out | Share |", "|---|---:|---:|---:|---:|"]
        for v in propagation[:20]:
            lines.append(f"| {v['vendor']} | {v['sites']} | {v['requests_gpc_on']} | "
                         f"{v['requests_with_optout']} | {v['share_with_optout']:.0%} |")
    if comparison:
        lines += ["", "## GPC behavior by vantage point", "",
                  "| Vantage | Sites | honors | declares_only | ignores |", "|---|---:|---:|---:|---:|"]
        for vtg in vantages:
            vc = Counter(r.get(vtg) for r in comparison if r.get(vtg))
            lines.append(f"| {vtg} | {sum(vc.values())} | {vc.get('honors', 0)} | "
                         f"{vc.get('declares_only', 0)} | {vc.get('ignores', 0)} |")
        some = [r["site"] for r in comparison if r["honors_only_some"]]
        lines += ["", f"Sites that honor GPC at some vantage points but not others: **{len(some)}**"
                  + (f" ({', '.join(some[:15])}{'…' if len(some) > 15 else ''})" if some else "")]
    if any("reject_verdict" in s for s in sites):
        rv = Counter(s["reject_verdict"] for s in sites if "reject_verdict" in s)
        lines += ["", "## Cookie banners: does 'Reject all' work? (A vs. C)", ""]
        lines += [f"- `{k}`: {n}" for k, n in rv.most_common()]
    if any("conflict_verdict" in s for s in sites):
        cv = Counter(s["conflict_verdict"] for s in sites if "conflict_verdict" in s)
        lines += ["", "## GPC vs. 'Accept all' conflict (B vs. D)", ""]
        lines += [f"- `{k}`: {n}" for k, n in cv.most_common()]
    lines += ["", "## Per-site detail", "",
              "| Site | Verdict | Trackers off→on | Trackers remaining | Cookies off→on | "
              "Declared opt-out (GPC on) | gpc.json |",
              "|---|---|---|---:|---|---|---|"]
    for s in gpc_sites:
        left = s.get("trackers_remaining")
        lines.append(f"| {s['site']} | `{s['verdict']}` | {s.get('trackers_A')}→{s.get('trackers_B')} | "
                     f"{'–' if left is None else f'{left:.0%}'} | "
                     f"{s.get('cookies_A')}→{s.get('cookies_B')} | {s.get('declared_optout_B')} | {s.get('gpc_json')} |")
    reduced = [s["trackers_remaining"] for s in gpc_sites
               if s["verdict"] in ("honors", "reduces_without_declaring") and s.get("trackers_remaining") is not None]
    if reduced:
        half = sum(r > 0.5 for r in reduced)
        lines += ["", f"Of the {len(reduced)} sites where tracking drops, {half} still load more than half of their "
                  "baseline tracker domains with GPC on. A drop is not the same as a full opt-out."]
    lines += ["", "> Verdicts describe browser-observable behavior only. Server-side sharing is invisible to this "
              "tool, so a clean result is not proof of compliance, and no verdict is a legal conclusion.", ""]
    return "\n".join(lines)

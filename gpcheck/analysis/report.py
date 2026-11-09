"""Write analysis outputs: CSV tables, a DuckDB database, and a Markdown report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .metrics import (Classifier, load_records, paired_stats, site_verdicts, vantage_comparison,
                      vendor_persistence, vendor_propagation)

VERDICT_TEXT = {
    "honors": "Declares an opt-out and tracking drops",
    "reduces_without_declaring": "Tracking drops, but no opt-out flag is set",
    "declares_only": "Declares an opt-out but keeps tracking (says vs. does gap)",
    "ignores": "No declared opt-out and no change in tracking",
    "no_tracking_baseline": "No trackers even with GPC off (nothing to stop)",
    "inconclusive": "Missing or failed visits",
}


PRIMARY_VANTAGE = "CA"


def analyze(input_paths, out_dir: str | Path, classifier: Classifier) -> dict:
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
    for k, rows in rows_by_vantage.items():
        for r in rows:
            r["vantage"] = k
    primary = PRIMARY_VANTAGE if PRIMARY_VANTAGE in by_vantage else sorted(by_vantage)[0] if by_vantage else None
    sites = rows_by_vantage.get(primary, [])
    primary_visits = by_vantage.get(primary, [])
    vendors = vendor_persistence(sites, primary_visits)
    propagation = vendor_propagation(primary_visits)
    stats = {k: paired_stats(rows) for k, rows in rows_by_vantage.items()}
    comparison = vantage_comparison(rows_by_vantage) if len(by_vantage) > 1 else []

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
    (out / "stats.json").write_text(json.dumps(stats, indent=2))

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
                           all_stats=stats)
    (out / "report.md").write_text(report)
    return {"sites": sites, "all_sites": all_rows, "vendors": vendors, "propagation": propagation,
            "comparison": comparison, "stats": stats, "out_dir": str(out)}


def _fmt_p(p: float | None) -> str:
    return "n/a (too few differing pairs)" if p is None else f"{p:.4g}"


PROPAGATION_TEXT = {
    "all_requests_carry_optout": "Every tracker request carries an opt-out signal",
    "some_requests_carry_optout": "Some tracker requests carry an opt-out signal",
    "no_optout_passed": "Trackers load with no opt-out signal attached",
    "no_tracker_data_requests": "No data-sending tracker requests with GPC on",
}


def render_report(sites, vendors, stats, visits, classifier, input_path, primary=None, propagation=(),
                  comparison=(), vantages=(), all_stats=None) -> str:
    gpc_sites = [s for s in sites if s["verdict"] is not None]
    verdicts = Counter(s["verdict"] for s in gpc_sites)
    total = len(gpc_sites)
    lines = [
        "# GPCheck results", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from `{input_path}`. "
        f"Tracker sources: {', '.join(classifier.trackers.sources)}.", "",
        f"Vantage points: {', '.join(vantages) or 'n/a'}. Sections below use **{primary}** unless noted.", "",
        f"**{len(sites)} sites, {len(visits)} visits** ({sum(v['status'] != 'ok' for v in visits)} failed).", "",
        "## GPC verdicts (condition A: GPC off vs. B: GPC on)", "",
        "| Verdict | Sites | Share | Meaning |", "|---|---:|---:|---|",
    ]
    for key, text in VERDICT_TEXT.items():
        n = verdicts.get(key, 0)
        lines.append(f"| `{key}` | {n} | {n / total:.0%} | {text} |" if total else f"| `{key}` | 0 | – | {text} |")
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
              "| Site | Verdict | Trackers off→on | Cookies off→on | Declared opt-out (GPC on) | gpc.json |",
              "|---|---|---|---|---|---|"]
    for s in gpc_sites:
        lines.append(f"| {s['site']} | `{s['verdict']}` | {s.get('trackers_A')}→{s.get('trackers_B')} | "
                     f"{s.get('cookies_A')}→{s.get('cookies_B')} | {s.get('declared_optout_B')} | {s.get('gpc_json')} |")
    lines += ["", "> Verdicts describe browser-observable behavior only. Server-side sharing is invisible to this "
              "tool, so a clean result is not proof of compliance, and no verdict is a legal conclusion.", ""]
    return "\n".join(lines)

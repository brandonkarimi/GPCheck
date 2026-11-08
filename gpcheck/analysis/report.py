"""Write analysis outputs: CSV tables, a DuckDB database, and a Markdown report."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .metrics import Classifier, load_records, paired_stats, site_verdicts, vendor_persistence

VERDICT_TEXT = {
    "honors": "Declares an opt-out and tracking drops",
    "reduces_without_declaring": "Tracking drops, but no opt-out flag is set",
    "declares_only": "Declares an opt-out but keeps tracking (says vs. does gap)",
    "ignores": "No declared opt-out and no change in tracking",
    "no_tracking_baseline": "No trackers even with GPC off (nothing to stop)",
    "inconclusive": "Missing or failed visits",
}


def analyze(input_path: str | Path, out_dir: str | Path, classifier: Classifier) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = load_records(input_path)
    visits = [classifier.visit(r) for r in records]
    sites = site_verdicts(visits)
    vendors = vendor_persistence(sites, visits)
    stats = paired_stats(sites)

    visits_df = pd.DataFrame([{k: v for k, v in x.items() if not k.startswith("_")} |
                              {"trackers": ";".join(x["_trackers"]), "vendors": ";".join(x["_vendors"])}
                              for x in visits])
    sites_df = pd.DataFrame([{k: (";".join(v) if isinstance(v, list) else v) for k, v in s.items()} for s in sites])
    vendors_df = pd.DataFrame(vendors, columns=["vendor", "sites_gpc_off", "sites_still_with_gpc_on", "persistence_rate"])
    requests_df = pd.DataFrame([{"site": x["site"], "condition": x["condition"], "run": x["run"],
                                 **{k: r.get(k) for k in ("url", "host", "etld1", "type", "page_index", "phase",
                                                          "sec_gpc", "third_party", "tracker", "counted")}}
                                for x in visits for r in x["_requests"]])
    visits_df.to_csv(out / "visits.csv", index=False)
    sites_df.to_csv(out / "sites.csv", index=False)
    vendors_df.to_csv(out / "vendors.csv", index=False)
    (out / "stats.json").write_text(json.dumps(stats, indent=2))

    import duckdb
    db_path = out / "gpcheck.duckdb"
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    for name, df in (("visits", visits_df), ("sites", sites_df), ("vendors", vendors_df), ("requests", requests_df)):
        if not df.empty:
            con.register("df_tmp", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM df_tmp")
            con.unregister("df_tmp")
    con.close()

    (out / "report.md").write_text(render_report(sites, vendors, stats, visits, classifier, input_path))
    return {"sites": sites, "vendors": vendors, "stats": stats, "out_dir": str(out)}


def _fmt_p(p: float | None) -> str:
    return "n/a (too few differing pairs)" if p is None else f"{p:.4g}"


def render_report(sites, vendors, stats, visits, classifier, input_path) -> str:
    gpc_sites = [s for s in sites if s["verdict"] is not None]
    verdicts = Counter(s["verdict"] for s in gpc_sites)
    total = len(gpc_sites)
    lines = [
        "# GPCheck results", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} from `{input_path}`. "
        f"Tracker sources: {', '.join(classifier.trackers.sources)}.", "",
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

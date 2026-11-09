"""End-to-end check against local fixture sites whose correct verdicts are known."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .analysis.metrics import Classifier, load_records
from .analysis.report import analyze
from .classify.cookies import seed_cookie_db
from .classify.trackers import build_tracker_list
from .config import parse_conditions, CrawlConfig
from .crawler.policy import check_policies
from .crawler.runner import crawl
from .fixtures.server import (EXPECTED_GPC, EXPECTED_POLICY, EXPECTED_PROPAGATION, EXPECTED_REJECT, RESOLVER_ARG,
                              FixtureServer)


def run_selftest(out: str | Path, chromium: str | None = None, dwell: float = 1.0,
                 runs: int = 2) -> tuple[bool, str]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    crawl_file = out / "crawl.jsonl"
    crawl_file.unlink(missing_ok=True)
    policy_file = out / "policy.jsonl"
    policy_file.unlink(missing_ok=True)
    cfg = CrawlConfig(dwell=dwell, subpages=1, workers=4, banner_wait=3.0, browser_args=[RESOLVER_ARG])
    if chromium:
        cfg.chromium_path = chromium
    with FixtureServer() as server:
        gpc_sites = [server.url(h) for h in EXPECTED_GPC]
        banner_sites = [server.url(h) for h in EXPECTED_REJECT]
        asyncio.run(crawl(gpc_sites, parse_conditions("A,B"), runs, cfg, crawl_file, log=lambda _: None,
                          vantage="local"))
        asyncio.run(crawl(banner_sites, parse_conditions("A,C"), runs, cfg, crawl_file, log=lambda _: None,
                          vantage="local"))
        asyncio.run(check_policies([server.url(h) for h in EXPECTED_POLICY], cfg, policy_file,
                                   log=lambda _: None, settle=0.6))
        port = server.port
    result = analyze(crawl_file, out / "analysis", Classifier(build_tracker_list(), seed_cookie_db()),
                     policy=load_records(policy_file))
    by_host = {s["site"].split("//")[1].split(":")[0]: s for s in result["sites"]}
    lines, ok = [f"Fixture server port {port}; results in {out}"], True
    for host, want in EXPECTED_GPC.items():
        got = by_host.get(host, {}).get("verdict")
        ok &= got == want
        lines.append(f"{'PASS' if got == want else 'FAIL'}  {host:16} GPC verdict    expected {want:26} got {got}")
    for host, want in EXPECTED_PROPAGATION.items():
        got = by_host.get(host, {}).get("propagation_verdict")
        ok &= got == want
        lines.append(f"{'PASS' if got == want else 'FAIL'}  {host:16} opt-out passed expected {want:26} got {got}")
    for host, want in EXPECTED_REJECT.items():
        got = by_host.get(host, {}).get("reject_verdict")
        ok &= got == want
        lines.append(f"{'PASS' if got == want else 'FAIL'}  {host:16} reject verdict expected {want:26} got {got}")
    for host, want in EXPECTED_POLICY.items():
        row = by_host.get(host, {})
        got = (row.get("policy_claim"), row.get("says_vs_does"))
        ok &= got == want
        lines.append(f"{'PASS' if got == want else 'FAIL'}  {host:16} policy claim   expected {want[0]:26} got {got[0]}"
                     f"  ({got[1]})")
    lines.append("ALL PASSED" if ok else "SOME CHECKS FAILED")
    return ok, "\n".join(lines)

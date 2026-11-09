import json

from gpcheck.analysis.metrics import Classifier
from gpcheck.analysis.report import analyze
from gpcheck.classify.cookies import seed_cookie_db
from gpcheck.classify.flows import parse_flow
from gpcheck.classify.trackers import build_tracker_list


def test_query_string_optout_flags():
    f = parse_flow("https://googleads.g.doubleclick.net/pagead?npa=1&us_privacy=1YYN&gpp_sid=7")
    assert f["opt_out_passed"] and f["google_npa"] and f["usp_opted_out"]
    assert f["privacy_signal_present"]


def test_full_event_without_optout():
    f = parse_flow("https://www.facebook.com/tr?id=1&ev=Purchase")
    assert f["event"] == "Purchase" and not f["opt_out_passed"] and not f["privacy_signal_present"]


def test_post_bodies():
    assert parse_flow("https://www.facebook.com/tr", "id=1&ev=PageView&dpo=LDU")["meta_ldu"]
    f = parse_flow("https://t.example/collect", json.dumps({"event": "x", "consent": {"us_privacy": "1YNN"}}))
    assert f["us_privacy"] == "1YNN" and not f["opt_out_passed"] and f["privacy_signal_present"]


def _visit(site, vantage, cond, run, tracker, usp):
    reqs = [{"url": f"https://{site}/", "type": "document", "page_index": 0, "phase": "pre_action",
             "sec_gpc": "1" if cond == "B" else None}]
    if tracker:
        reqs.append({"url": "https://www.google-analytics.com/g/collect?en=page_view", "type": "fetch",
                     "page_index": 0, "phase": "pre_action", "sec_gpc": "1" if cond == "B" else None})
    return {"site": site, "url": f"https://{site}/", "final_url": f"https://{site}/", "condition": cond,
            "gpc": cond == "B", "run": run, "status": "ok", "vantage": vantage, "requests": reqs,
            "cookies": [], "signals": {"usp": {"uspString": usp}}}


def test_vantage_comparison(tmp_path):
    ca, tx = tmp_path / "ca.jsonl", tmp_path / "tx.jsonl"
    with ca.open("w", encoding="utf-8") as fh:
        for run in range(2):
            fh.write(json.dumps(_visit("shop.com", "CA", "A", run, True, "1YNN")) + "\n")
            fh.write(json.dumps(_visit("shop.com", "CA", "B", run, False, "1YYN")) + "\n")
    with tx.open("w", encoding="utf-8") as fh:
        for run in range(2):
            fh.write(json.dumps(_visit("shop.com", "TX", "A", run, True, "1YNN")) + "\n")
            fh.write(json.dumps(_visit("shop.com", "TX", "B", run, True, "1YNN")) + "\n")
    result = analyze([ca, tx], tmp_path / "out", Classifier(build_tracker_list(), seed_cookie_db()))
    row = result["comparison"][0]
    assert row["CA"] == "honors" and row["TX"] == "ignores" and row["honors_only_some"]
    tx_row = next(r for r in result["all_sites"] if r["vantage"] == "TX")
    assert tx_row["propagation_verdict"] == "no_optout_passed"
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "GPC behavior by vantage point" in report and "Is the opt-out passed to vendors" in report

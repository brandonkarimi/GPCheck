import csv
import json

import pytest

from gpcheck.analysis.metrics import Classifier, blocked_reason, cohen_kappa, wilson
from gpcheck.analysis.report import analyze, load_site_column, write_sample
from gpcheck.classify.cookies import seed_cookie_db
from gpcheck.classify.trackers import build_tracker_list


def _visit(site, cond, run, tracker, usp="1YNN", status=200, title="Home"):
    reqs = [{"url": f"https://{site}/", "type": "document", "page_index": 0, "phase": "pre_action"}]
    if tracker:
        reqs.append({"url": "https://www.google-analytics.com/g/collect?en=page_view", "type": "fetch",
                     "page_index": 0, "phase": "pre_action"})
    return {"site": site, "url": f"https://{site}/", "final_url": f"https://{site}/", "condition": cond,
            "gpc": cond == "B", "run": run, "status": "ok", "vantage": "CA", "requests": reqs,
            "cookies": [], "signals": {"usp": {"uspString": usp}},
            "pages": [{"url": f"https://{site}/", "status": status}], "title": title}


def _crawl_file(tmp_path, visits):
    path = tmp_path / "crawl.jsonl"
    path.write_text("".join(json.dumps(v) + "\n" for v in visits), encoding="utf-8")
    return path


def _analyze(tmp_path, visits, **kwargs):
    return analyze(_crawl_file(tmp_path, visits), tmp_path / "out",
                   Classifier(build_tracker_list(), seed_cookie_db()), **kwargs)


def test_blocked_reason():
    assert blocked_reason({"pages": [{"status": 403}]})
    assert blocked_reason({"pages": [{"status": 200}], "title": "Just a moment..."})
    assert blocked_reason({"pages": [{"status": 200}], "title": "Breaking news"}) is None
    assert blocked_reason({}) is None  # records from older crawls have neither field


def test_blocked_site_is_inconclusive_not_clean(tmp_path):
    visits = [_visit("wall.com", cond, run, False, status=403, title="Access Denied")
              for cond in "AB" for run in range(2)]
    result = _analyze(tmp_path, visits)
    assert result["sites"][0]["verdict"] == "inconclusive"
    assert "4 blocked by bot protection" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def test_partly_blocked_site_is_inconclusive(tmp_path):
    visits = [_visit("half.com", cond, 0, True) for cond in "AB"]
    visits += [_visit("half.com", cond, 1, False, status=429, title="Access to this page has been denied")
               for cond in "AB"]
    assert _analyze(tmp_path, visits)["sites"][0]["verdict"] == "inconclusive"


def test_trackers_remaining(tmp_path):
    visits = [_visit("shop.com", "A", r, True) for r in range(2)]
    visits += [_visit("shop.com", "B", r, False, "1YYN") for r in range(2)]
    row = _analyze(tmp_path, visits)["sites"][0]
    assert row["verdict"] == "honors" and row["trackers_remaining"] == 0.0


def test_wilson_and_kappa():
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.237, abs=0.001) and high == pytest.approx(0.763, abs=0.001)
    assert wilson(0, 0) is None
    assert cohen_kappa([("honors", "honors"), ("ignores", "ignores")]) == 1.0
    assert cohen_kappa([("honors", "ignores"), ("ignores", "honors")]) == -1.0


def test_categories_manual_check_and_sample(tmp_path):
    visits = []
    for run in range(2):
        visits += [_visit("shop.com", "A", run, True), _visit("shop.com", "B", run, False, "1YYN"),
                   _visit("news.com", "A", run, True), _visit("news.com", "B", run, True)]
    cats = tmp_path / "cats.csv"
    cats.write_text("site,category\nshop.com,retail\nhttps://www.news.com/,news\n", encoding="utf-8")
    manual = tmp_path / "manual.csv"
    manual.write_text("site,manual_verdict,notes\nshop.com,honors,\nnews.com,declares_only,x\n", encoding="utf-8")
    result = _analyze(tmp_path, visits, categories=load_site_column(cats, "category"),
                      manual=load_site_column(manual, "manual_verdict"))
    assert {s["site"]: s["category"] for s in result["sites"]} == {"shop.com": "retail", "news.com": "news"}
    assert result["validation"]["n"] == 2 and result["validation"]["agree"] == 1
    assert result["validation"]["disagreements"][0]["site"] == "news.com"
    report = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert "GPC verdicts by site category" in report and "agree on **1 of 2**" in report

    sheet = tmp_path / "sheet.csv"
    assert write_sample(tmp_path / "out" / "sites.csv", sheet, 5, seed=1) == ["news.com", "shop.com"]
    with sheet.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert all(r["manual_verdict"] == "" for r in rows) and "verdict" not in rows[0]

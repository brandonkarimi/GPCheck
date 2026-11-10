import json

import pytest

from gpcheck.analysis.metrics import Classifier, blocked_reason, wilson
from gpcheck.analysis.report import analyze, load_site_column
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


def test_wilson():
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.237, abs=0.001) and high == pytest.approx(0.763, abs=0.001)
    assert wilson(0, 0) is None


def test_categories(tmp_path):
    visits = []
    for run in range(2):
        visits += [_visit("shop.com", "A", run, True), _visit("shop.com", "B", run, False, "1YYN"),
                   _visit("news.com", "A", run, True), _visit("news.com", "B", run, True)]
    cats = tmp_path / "cats.csv"
    cats.write_text("site,category\nshop.com,retail\nhttps://www.news.com/,news\n", encoding="utf-8")
    result = _analyze(tmp_path, visits, categories=load_site_column(cats, "category"))
    assert {s["site"]: s["category"] for s in result["sites"]} == {"shop.com": "retail", "news.com": "news"}
    assert "GPC verdicts by site category" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")

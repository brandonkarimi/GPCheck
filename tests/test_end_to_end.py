"""Crawl the local ground-truth sites with a real browser and check every verdict."""

from gpcheck.config import CrawlConfig
from gpcheck.crawler.check import run_check
from gpcheck.selftest import run_selftest


def test_gpc_emulation_reaches_every_layer(chromium):
    result = run_check(CrawlConfig(chromium_path=chromium))
    assert result["ok"], result


def test_fixture_verdicts(chromium, tmp_path):
    ok, report = run_selftest(tmp_path, chromium)
    assert ok, report

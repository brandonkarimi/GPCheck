"""Command-line interface: `gpcheck --help`."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from .config import CrawlConfig, parse_conditions

app = typer.Typer(add_completion=False, help="Measure whether websites honor Global Privacy Control.")


def _cfg(dwell: float, subpages: int, workers: int, headful: bool, chromium: Optional[str],
         screenshots: Optional[Path]) -> CrawlConfig:
    cfg = CrawlConfig(dwell=dwell, subpages=subpages, workers=workers, headful=headful,
                      screenshots_dir=str(screenshots) if screenshots else None)
    if chromium:
        cfg.chromium_path = chromium
    return cfg


@app.command()
def crawl(
    sites: Path = typer.Argument(..., help="File with one domain or URL per line (CSV rank,domain also works)"),
    out: Path = typer.Option(Path("results/crawl.jsonl"), help="JSONL output (re-running resumes)"),
    conditions: str = typer.Option("A,B", help="A=GPC off, B=GPC on, C=reject banner, D=GPC on + accept banner"),
    runs: int = typer.Option(3, help="Paired repetitions per site"),
    dwell: float = typer.Option(15.0, help="Seconds on each page"),
    subpages: int = typer.Option(2, help="Internal pages per site after the homepage"),
    workers: int = typer.Option(4, help="Sites crawled in parallel"),
    limit: int = typer.Option(0, help="Only the first N sites (0 = all)"),
    seed: int = typer.Option(0, help="Seed for randomizing condition order"),
    headful: bool = typer.Option(False, help="Show the browser (needs a display or Xvfb)"),
    chromium: Optional[str] = typer.Option(None, envvar="GPCHECK_CHROMIUM", help="Path to a Chromium binary"),
    screenshots: Optional[Path] = typer.Option(None, help="Directory for homepage screenshots"),
):
    """Visit every site under each condition and record requests, cookies and opt-out signals."""
    from .crawler.runner import crawl as run_crawl, load_sites

    site_list = load_sites(sites)
    if limit:
        site_list = site_list[:limit]
    conds = parse_conditions(conditions)
    cfg = _cfg(dwell, subpages, workers, headful, chromium, screenshots)
    typer.echo(f"Crawling {len(site_list)} sites x {len(conds)} conditions x {runs} runs -> {out}")
    asyncio.run(run_crawl(site_list, conds, runs, cfg, out, seed=seed, log=typer.echo))


@app.command()
def analyze(
    crawl_file: Path = typer.Argument(Path("results/crawl.jsonl")),
    out: Path = typer.Option(Path("results/analysis"), help="Output directory"),
    trackers: list[Path] = typer.Option([], help="Extra tracker lists (DuckDuckGo tds.json, Disconnect, .txt)"),
    cookie_db: Optional[Path] = typer.Option(None, help="Open Cookie Database CSV"),
    lists_dir: Optional[Path] = typer.Option(Path("data/lists"), help="Auto-load lists downloaded by `gpcheck lists`"),
):
    """Classify trackers and cookies, compute verdicts and statistics, write a report."""
    from .analysis.metrics import Classifier
    from .analysis.report import analyze as run_analyze
    from .classify.cookies import load_open_cookie_database, seed_cookie_db
    from .classify.trackers import build_tracker_list

    tracker_paths = list(trackers)
    if lists_dir and lists_dir.exists():
        for name in ("ddg_tds.json", "disconnect_services.json"):
            if (lists_dir / name).exists():
                tracker_paths.append(lists_dir / name)
        if cookie_db is None and (lists_dir / "open_cookie_database.csv").exists():
            cookie_db = lists_dir / "open_cookie_database.csv"
    db = seed_cookie_db()
    if cookie_db:
        load_open_cookie_database(cookie_db, db)
    result = run_analyze(crawl_file, out, Classifier(build_tracker_list(tracker_paths), db))
    typer.echo(f"Wrote {out}/report.md, sites.csv, vendors.csv, visits.csv, gpcheck.duckdb")
    typer.echo(json.dumps(result["stats"], indent=2))


@app.command("check-gpc")
def check_gpc(chromium: Optional[str] = typer.Option(None, envvar="GPCHECK_CHROMIUM")):
    """Verify GPC emulation reaches navigations, subresources, cross-site iframes and navigator."""
    from .crawler.check import run_check

    result = run_check(_cfg(1, 0, 1, False, chromium, None))
    typer.echo(json.dumps(result, indent=2))
    raise typer.Exit(0 if result["ok"] else 1)


@app.command()
def selftest(chromium: Optional[str] = typer.Option(None, envvar="GPCHECK_CHROMIUM"),
             out: Path = typer.Option(Path("results/selftest"))):
    """Crawl the local ground-truth fixture sites and confirm every verdict is correct."""
    from .selftest import run_selftest

    ok, report = run_selftest(out, chromium)
    typer.echo(report)
    raise typer.Exit(0 if ok else 1)


@app.command()
def lists(dest: Path = typer.Option(Path("data/lists")),
          tranco: int = typer.Option(0, help="Also download the Tranco top-N site list (0 = skip)")):
    """Download DuckDuckGo Tracker Radar, Disconnect, the Open Cookie Database (and Tranco)."""
    from .lists import fetch_lists, fetch_tranco

    for p in fetch_lists(dest):
        typer.echo(f"saved {p}")
    if tranco:
        typer.echo(f"saved {fetch_tranco(Path('data/sites') / f'tranco_top{tranco}.csv', tranco)}")


if __name__ == "__main__":
    app()

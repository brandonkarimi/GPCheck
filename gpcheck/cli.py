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
    vantage: str = typer.Option("CA", help="Label for where this crawl runs from, e.g. CA, CO, TX, FL"),
    geo: bool = typer.Option(True, help="Look up this machine's city/region (IP is not stored)"),
):
    """Visit every site under each condition and record requests, cookies and opt-out signals."""
    from .crawler.runner import crawl as run_crawl, load_sites, lookup_geo

    site_list = load_sites(sites)
    if limit:
        site_list = site_list[:limit]
    conds = parse_conditions(conditions)
    cfg = _cfg(dwell, subpages, workers, headful, chromium, screenshots)
    location = lookup_geo() if geo else None
    if location:
        typer.echo(f"Vantage {vantage}: this machine appears to be in "
                   f"{location.get('city')}, {location.get('region')}, {location.get('country')}")
        if vantage.upper() == "CA" and location.get("region") != "California":
            typer.secho("Warning: --vantage CA but this IP does not geolocate to California "
                        "(VPN on? wrong machine?)", fg=typer.colors.YELLOW)
    typer.echo(f"Crawling {len(site_list)} sites x {len(conds)} conditions x {runs} runs -> {out}")
    asyncio.run(run_crawl(site_list, conds, runs, cfg, out, seed=seed, log=typer.echo,
                          vantage=vantage, geo=location))


@app.command()
def analyze(
    crawl_files: list[Path] = typer.Argument(None, help="One or more crawl files, e.g. one per state "
                                             "(default: results/crawl.jsonl)"),
    out: Path = typer.Option(Path("results/analysis"), help="Output directory"),
    trackers: list[Path] = typer.Option([], help="Extra tracker lists (DuckDuckGo tds.json, Disconnect, .txt)"),
    cookie_db: Optional[Path] = typer.Option(None, help="Open Cookie Database CSV"),
    lists_dir: Optional[Path] = typer.Option(Path("data/lists"), help="Auto-load lists downloaded by `gpcheck lists`"),
    categories: Optional[Path] = typer.Option(None, help="CSV with columns site,category for a per-category table"),
    manual: Optional[Path] = typer.Option(None, help="Hand-checked sheet from `gpcheck sample` (site,manual_verdict)"),
    policy: Optional[Path] = typer.Option(Path("results/policy.jsonl"), help="Output of `gpcheck policy` (used if it exists)"),
):
    """Classify trackers and cookies, compute verdicts and statistics, write a report."""
    from .analysis.metrics import Classifier, load_records
    from .analysis.report import analyze as run_analyze, load_site_column
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
    result = run_analyze(crawl_files or [Path("results/crawl.jsonl")], out,
                         Classifier(build_tracker_list(tracker_paths), db),
                         categories=load_site_column(categories, "category") if categories else None,
                         manual=load_site_column(manual, "manual_verdict") if manual else None,
                         policy=load_records(policy) if policy and policy.exists() else None)
    typer.echo(f"Wrote {out}/report.md, CSV tables and gpcheck.duckdb")
    typer.echo(json.dumps(result["stats"], indent=2))


@app.command()
def policy(
    sites: Path = typer.Argument(..., help="File with one domain or URL per line"),
    out: Path = typer.Option(Path("results/policy.jsonl"), help="JSONL output (re-running resumes)"),
    workers: int = typer.Option(4, help="Sites checked in parallel"),
    limit: int = typer.Option(0, help="Only the first N sites (0 = all)"),
    headful: bool = typer.Option(False, help="Show the browser"),
    chromium: Optional[str] = typer.Option(None, envvar="GPCHECK_CHROMIUM", help="Path to a Chromium binary"),
):
    """Record each site's opt-out link and what its privacy policy says about GPC."""
    from .crawler.policy import check_policies
    from .crawler.runner import load_sites

    site_list = load_sites(sites)
    if limit:
        site_list = site_list[:limit]
    asyncio.run(check_policies(site_list, _cfg(0, 0, workers, headful, chromium, None), out, log=typer.echo))
    typer.echo(f"Wrote {out}; `gpcheck analyze` will pick it up.")


@app.command()
def sample(
    sites_csv: Path = typer.Argument(Path("results/analysis/sites.csv"), help="sites.csv written by `gpcheck analyze`"),
    out: Path = typer.Option(Path("results/manual_check.csv"), help="Sheet to fill in by hand"),
    n: int = typer.Option(20, help="Number of sites to draw"),
    seed: int = typer.Option(0, help="Seed for the random draw"),
):
    """Draw a random sample of sites to verify by hand in a GPC-enabled browser."""
    from .analysis.report import VERDICT_TEXT, write_sample

    if out.exists():
        typer.secho(f"{out} already exists; not overwriting (it may hold your manual verdicts).", fg=typer.colors.RED)
        raise typer.Exit(1)
    chosen = write_sample(sites_csv, out, n, seed)
    typer.echo(f"Wrote {len(chosen)} sites to {out}. Fill in manual_verdict with one of: "
               f"{', '.join(k for k in VERDICT_TEXT if k != 'inconclusive')}; "
               f"then run `gpcheck analyze --manual {out}`.")


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


@app.command()
def sites(
    candidates: Path = typer.Option(Path("data/sites/candidates.csv"), help="Hand-drawn CSV: site,category"),
    n: int = typer.Option(500, help="Number of sites to keep"),
    out: Path = typer.Option(Path("data/sites/study_500.txt"), help="Site list for `gpcheck crawl`"),
    categories: Path = typer.Option(Path("data/sites/study_categories.csv"), help="Matching site,category file"),
):
    """Build the study sample: the candidates that rank highest in the Tranco list."""
    import csv

    from .lists import build_site_list, fetch_tranco

    tranco = Path("data/sites/tranco_top1000000.csv")
    if not tranco.exists():
        typer.echo("Downloading the Tranco list...")
        fetch_tranco(tranco, 1_000_000)
    rows = build_site_list(candidates, tranco, n)
    out.write_text("# Study sample: candidates.csv ranked by Tranco (built by `gpcheck sites`)\n"
                   + "".join(f"{site}\n" for _, site, _ in rows), encoding="utf-8")
    with categories.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["site", "category", "tranco_rank"])
        writer.writerows([site, category, rank] for rank, site, category in rows)
    typer.echo(f"Wrote {len(rows)} sites to {out} and {categories} (Tranco ranks {rows[0][0]} to {rows[-1][0]})")


if __name__ == "__main__":
    app()

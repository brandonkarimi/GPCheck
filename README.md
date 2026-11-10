# GPCheck

Checks whether websites honor the Global Privacy Control (GPC) opt-out signal required by California's CCPA. It crawls sites with GPC off and on and compares trackers, tracking cookies and declared opt-out status.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m playwright install chromium
```

## Usage

```bash
gpcheck check-gpc                     # confirm GPC is being sent
gpcheck selftest                      # run against local test sites
gpcheck crawl data/sites/sample.txt   # crawl (writes results/crawl.jsonl)
gpcheck analyze                       # report in results/analysis/
```

Run real crawls from a California IP address. The study sample is the 500 most popular sites from a hand-drawn list of US consumer sites, ranked by Tranco:

```bash
gpcheck sites                         # writes data/sites/study_500.txt and study_categories.csv
gpcheck crawl data/sites/study_500.txt --out results/study.jsonl
```

To compare what sites say with what they do, record each site's opt-out link and privacy policy. The next `gpcheck analyze` adds a "claims vs. measured behavior" section:

```bash
gpcheck policy data/sites/sample.txt  # writes results/policy.jsonl
```

To break verdicts down by site category, pass a `site,category` CSV:

```bash
gpcheck analyze --categories data/sites/sample_categories.csv
```

How it works: [docs/METHODOLOGY.md](docs/METHODOLOGY.md)

Results of the 500-site study: [docs/RESULTS.md](docs/RESULTS.md)

Pilot results on 30 sites: [docs/PILOT.md](docs/PILOT.md)

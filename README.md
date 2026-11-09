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

Run real crawls from a California IP address. To compare states, crawl the same list from each location and analyze the files together:

```bash
gpcheck crawl data/sites/sample.txt --vantage TX --out results/tx.jsonl
gpcheck analyze results/crawl.jsonl results/tx.jsonl
```

To compare what sites say with what they do, record each site's opt-out link and privacy policy. The next `gpcheck analyze` adds a "claims vs. measured behavior" section:

```bash
gpcheck policy data/sites/sample.txt  # writes results/policy.jsonl
```

To break verdicts down by site category, pass a `site,category` CSV:

```bash
gpcheck analyze --categories data/sites/sample_categories.csv
```

To validate the automated verdicts by hand, draw a random sample, fill in the `manual_verdict` column while checking each site in a GPC-enabled browser, then feed the sheet back in. The report gains an agreement rate and Cohen's kappa:

```bash
gpcheck sample --n 20                 # writes results/manual_check.csv
gpcheck analyze --manual results/manual_check.csv
```

How it works: [docs/METHODOLOGY.md](docs/METHODOLOGY.md)

Pilot results on 30 sites: [docs/PILOT.md](docs/PILOT.md)

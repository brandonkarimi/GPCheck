# GPCheck

Checks whether websites honor the Global Privacy Control (GPC) opt-out signal required by California's CCPA. It crawls sites with GPC off and on and compares trackers, tracking cookies and declared opt-out status.

## Setup

```bash
make install
```

## Usage

```bash
gpcheck check-gpc                     # confirm GPC is being sent
gpcheck selftest                      # run against local test sites
gpcheck crawl data/sites/sample.txt   # crawl (writes results/crawl.jsonl)
gpcheck analyze                       # report in results/analysis/
```

Run real crawls from a California IP address.

How it works: [docs/METHODOLOGY.md](docs/METHODOLOGY.md)

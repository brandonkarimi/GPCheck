SITES ?= data/sites/sample.txt
RUNS ?= 3
OUT ?= results/crawl.jsonl

.PHONY: install test selftest check lists crawl analyze

install:
	pip install -e ".[dev]"
	python -m playwright install $(if $(filter Linux,$(shell uname -s)),--with-deps,) chromium

test:
	pytest -q

selftest:
	gpcheck selftest

check:
	gpcheck check-gpc

lists:
	gpcheck lists --tranco 1000

crawl:
	gpcheck crawl $(SITES) --out $(OUT) --runs $(RUNS)

analyze:
	gpcheck analyze $(OUT) --out results/analysis

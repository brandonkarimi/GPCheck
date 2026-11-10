# Pilot crawl

A small run to test the pipeline on real sites before the full study. Results are reported in aggregate only: no site has been re-verified by hand yet, so none is named here (see Ethics in [METHODOLOGY.md](METHODOLOGY.md)).

## Setup

- **Date:** 9 November 2026
- **Sites:** the 30 in `data/sites/sample.txt` (news, retail, health, travel, real estate, local)
- **Design:** conditions A, B, C and D, three runs each, 360 visits in about 95 minutes
- **Vantage:** a California IP address
- **Lists:** DuckDuckGo Tracker Radar, Disconnect, Open Cookie Database, plus the bundled seed lists

```bash
gpcheck lists
gpcheck crawl data/sites/sample.txt --conditions A,B,C,D
gpcheck policy data/sites/sample.txt
gpcheck analyze --categories data/sites/sample_categories.csv
```

## Results

| Verdict | Sites | Share | 95% CI |
|---|---:|---:|---:|
| `honors` | 10 | 33% | 19%–51% |
| `reduces_without_declaring` | 4 | 13% | 5%–30% |
| `declares_only` | 2 | 7% | 2%–21% |
| `ignores` | 1 | 3% | 1%–17% |
| `inconclusive` | 13 | 43% | 27%–61% |

Across the 17 sites with a verdict:

- **Tracker domains** fell from a mean of 86.9 with GPC off to 38.6 with GPC on (Wilcoxon one-sided p = 0.0005).
- **Tracking cookies** fell from a mean of 172.5 to 48.1 (p = 0.0003).
- **No site stopped tracking entirely.** Of the 14 sites where tracking dropped, 6 still loaded more than half of their baseline tracker domains with GPC on.
- **Opt-out propagation was partial at best.** No site attached an opt-out signal to every tracker request; on 10 sites no tracker request carried one.
- **Policy claims:** 7 privacy policies commit to honoring GPC. Tracking dropped on 5 of those sites and did not drop on 2.

## What the pilot showed about the method

1. **Bot protection is the main threat to coverage.** 12 of 30 sites served a block page (HTTP 403 or 429) on some or all visits, and one refused the connection. Before this run, those visits were recorded as successful and would have been scored as sites with little or no tracking. They are now detected and scored `inconclusive`. A site with any blocked A/B visit is excluded entirely, since the visits that do get through may be degraded.
2. **Heavy pages never fire `load`.** Ad-heavy news homepages timed out waiting for the `load` event while thousands of requests were already flowing. Navigation now waits for it but does not require it.
3. **`honors` is a low bar.** The verdict requires only a drop beyond the noise floor. Several `honors` sites still load a large majority of their trackers. The report now shows the share of tracker domains remaining, and the full study should report it next to the verdict.
4. **Banner conditions add little for US sites.** From California, 16 of 17 sites showed no cookie banner, so conditions C and D doubled the crawl time for almost no data. The full study should run A and B only, with C and D on a subsample.
5. **Vendor names need merging.** The same company appears under several names from different lists (for example "Google", "Google LLC" and "Google Ads"), which splits the per-vendor tables.
6. **Short policy pages are unreliable.** Some privacy links lead to a hub page, not the policy text, so "never mentions GPC" is weaker evidence than "claims to honor GPC".

## Limits of this run

- Thirty sites is too few for the per-category table or the intervals to mean much.
- Nothing has been checked by hand.
- The 13 inconclusive sites are not a random subset: large retailers and travel sites are over-represented, so the verdict shares above describe sites without aggressive bot protection.

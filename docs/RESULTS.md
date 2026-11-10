# Results

Do popular US websites honor the Global Privacy Control signal when visited from California? This page reports the 500-site study in aggregate. No site is named: the verdicts are automated and have not yet been verified by hand (see Ethics in [METHODOLOGY.md](METHODOLOGY.md)).

## Summary

- **364 of 500 sites could be measured.** The other 136 were inconclusive, almost all because bot protection blocked the crawler.
- **GPC roughly halves visible tracking, but rarely stops it.** Across measured sites, mean tracker domains fell from 84.4 to 44.0 (48%) and tracking cookies from 176.9 to 60.3 (66%). Only 3 sites went from some trackers to none.
- **About a quarter of measured sites do not reduce tracking.** 86 of 364 (24%) showed no drop beyond run-to-run noise; 47 of them still told the browser the user was opted out.
- **Policy and practice diverge on 25 sites.** 141 privacy policies commit to honoring GPC. Tracking dropped on 116 of those sites and did not drop on 25 (18%).
- **The opt-out is seldom passed on.** No site attached an opt-out signal to every tracker request, and on 150 sites no tracker request carried one.

## Setup

- **Dates:** 9–10 November 2026
- **Sites:** `data/sites/study_500.txt`, 500 popular US consumer-facing commercial sites in 13 categories
- **Design:** conditions A (GPC off) and B (GPC on), three paired runs per site, 3,000 visits
- **Vantage:** a California IP address
- **Lists:** DuckDuckGo Tracker Radar, Disconnect, Open Cookie Database and the bundled seed lists (4,211 tracker domains)

```bash
gpcheck sites
gpcheck crawl data/sites/study_500.txt --conditions A,B --out results/study.jsonl
gpcheck policy data/sites/study_500.txt --out results/study_policy.jsonl
gpcheck analyze results/study.jsonl --policy results/study_policy.jsonl \
    --categories data/sites/study_categories.csv --out results/study_analysis
```

Of the 3,000 visits, 2,213 loaded normally, 587 returned a bot-protection page and 200 failed (mostly connections refused by the site).

## Verdicts

| Verdict | Sites | Share of 500 | 95% CI | Share of measured |
|---|---:|---:|---:|---:|
| `honors`: declares an opt-out and tracking drops | 196 | 39% | 35%–44% | 54% |
| `reduces_without_declaring`: tracking drops, nothing declared | 71 | 14% | 11%–18% | 20% |
| `declares_only`: declares an opt-out, tracking does not drop | 47 | 9% | 7%–12% | 13% |
| `ignores`: nothing declared, no drop | 39 | 8% | 6%–10% | 11% |
| `no_tracking_baseline`: no trackers even with GPC off | 11 | 2% | 1%–4% | 3% |
| `inconclusive`: blocked or failed | 136 | 27% | 23%–31% | – |

Intervals are 95% Wilson score intervals.

## How much tracking remains

A verdict of `honors` only means tracking dropped by more than the noise between repeated baseline runs. It does not mean tracking stopped.

- Across the 364 measured sites, the median site still loaded 62% of its baseline tracker domains with GPC on.
- Of the 267 sites where tracking dropped, 142 (53%) still loaded more than half of their baseline tracker domains.
- Tracker domains fell from a mean of 84.4 to 44.0 (one-sided Wilcoxon signed-rank p < 0.001), and tracking cookies from 176.9 to 60.3 (p < 0.001).
- 58 of the 364 measured sites publish `/.well-known/gpc.json`.

## Policy claims vs. measured behavior

The policy check could read 368 of the 500 sites; 132 failed or were blocked.

| What the privacy policy says about GPC | Sites | With an opt-out link |
|---|---:|---:|
| Commits to honoring GPC or opt-out preference signals | 141 | 136 |
| Says GPC is not honored | 4 | 4 |
| Mentions GPC without a clear commitment | 17 | 15 |
| Never mentions GPC | 146 | 115 |
| No policy found or page unreadable | 60 | 38 |

Joined to the measured verdicts (344 sites with both):

| Policy vs. behavior | Sites |
|---|---:|
| Policy commits to GPC, and tracking dropped | 116 |
| Policy commits to GPC, but tracking did not drop | 25 |
| No commitment, and tracking dropped | 144 |
| No commitment, and tracking did not drop | 59 |

- The 25 sites in the second row are the policy-relevant finding: a public commitment contradicted by observed behavior. Each needs its policy sentence and its traffic checked by hand before any conclusion is drawn about it.
- 22 sites neither reduced tracking under GPC nor showed a "Do Not Sell or Share" or "Your Privacy Choices" link.

## Which vendors keep loading

Share of sites where a vendor that loads with GPC off still loads with GPC on (ten most common vendors):

| Vendor | Sites with GPC off | Still loads with GPC on | Persistence |
|---|---:|---:|---:|
| Google | 347 | 329 | 95% |
| Microsoft | 256 | 160 | 62% |
| Adobe | 216 | 158 | 73% |
| The Trade Desk | 208 | 137 | 66% |
| Amazon | 204 | 151 | 74% |
| Magnite | 201 | 134 | 67% |
| Index Exchange | 199 | 128 | 64% |
| Tapad | 195 | 115 | 59% |
| LiveRamp | 194 | 120 | 62% |
| PubMatic | 192 | 132 | 69% |

Meta stands out in the other direction: it loaded on 187 sites with GPC off and on only 55 (29%) with GPC on. A vendor loading is not proof of a sale or sharing of data; some of these requests serve analytics, fraud prevention or site delivery.

## Is the opt-out passed to vendors?

With GPC on, each data-sending tracker request was checked for an opt-out signal (`us_privacy`, a GPC parameter, Google `npa`/`rdp`/`ltd`, Meta `LDU`).

| Result | Sites |
|---|---:|
| Every tracker request carries an opt-out | 0 |
| Some tracker requests carry an opt-out | 205 |
| No tracker request carries an opt-out | 150 |
| No data-sending tracker requests | 22 |

Among the largest vendors, the share of requests carrying an opt-out ranged from 0% (Adobe, LiveRamp, DoubleVerify, Integral Ad Science) through 7% (Google) to 34% (The Trade Desk). A vendor may also learn the opt-out through a channel the browser cannot see.

## By category

| Category | Sites | Honors | Reduces, no declaration | Declares only | Ignores | No tracking | Inconclusive |
|---|---:|---:|---:|---:|---:|---:|---:|
| News | 104 | 70 | 2 | 9 | 1 | 0 | 22 |
| Retail | 101 | 13 | 20 | 7 | 12 | 5 | 44 |
| Entertainment | 49 | 19 | 8 | 8 | 7 | 2 | 5 |
| Lifestyle | 42 | 32 | 3 | 4 | 0 | 0 | 3 |
| Finance | 40 | 10 | 11 | 8 | 2 | 1 | 8 |
| Technology and telecom | 37 | 8 | 12 | 0 | 7 | 1 | 9 |
| Travel | 34 | 7 | 3 | 2 | 5 | 1 | 16 |
| Health | 24 | 16 | 3 | 1 | 1 | 0 | 3 |
| Food | 18 | 8 | 2 | 1 | 2 | 0 | 5 |
| Automotive | 16 | 3 | 2 | 1 | 0 | 0 | 10 |
| Sports | 14 | 6 | 2 | 3 | 0 | 1 | 2 |
| Jobs and education | 11 | 3 | 1 | 2 | 2 | 0 | 3 |
| Real estate | 10 | 1 | 2 | 1 | 0 | 0 | 6 |

Ad-funded publishers (news, lifestyle, health) mostly declare an opt-out and reduce tracking, which fits their use of consent-management platforms. Retail, travel, automotive and real estate are the hardest to measure: around half of those sites blocked the crawler. The smaller categories have too few sites to compare.

## Limitations

- **Not yet validated by hand.** The verdicts are automated. `gpcheck sample` and [MANUAL_CHECK.md](MANUAL_CHECK.md) are in place for a blind manual check, and this page will be updated with the agreement rate.
- **Bot protection removes 27% of the sample, and not at random.** Large retailers and travel sites are over-represented among inconclusive sites, so the shares above describe sites that let an automated browser in.
- **Only browser-visible behavior is measured.** Server-to-server sharing is invisible, so a clean result is not proof of compliance. A persisting tracker request is also not proof of a sale.
- **The sample is hand-drawn.** Sites come from a candidate list of well-known US consumer sites ranked by Tranco, not a random draw from the web.
- **Policy text is read by keyword.** Policies split across pages or worded unusually can be misclassified.
- **No verdict is a legal conclusion.** Whether a site is a covered business, and whether a given request is a sale or sharing, are outside what this tool can determine.

# Methodology

## Overview

California's CCPA (as amended by the CPRA) requires covered businesses to treat a browser's Global Privacy Control (GPC) signal as a request to opt out of the sale or sharing of personal information (11 CCR §7025). GPCheck tests whether sites actually do this. It visits each site under controlled conditions, once with GPC off and once with GPC on, and compares what the site does: third-party tracker requests, tracking cookies, and the opt-out status the site itself reports.

## Research questions

1. Among popular sites visited from California, what fraction change their tracking behavior when GPC is on?
2. Do sites that *declare* an opt-out (USP/GPP strings, CMP cookies, `/.well-known/gpc.json`) actually reduce tracking?
3. Which third parties keep receiving requests after the opt-out, and which CMPs and site categories are associated with non-compliance?
4. Does clicking "Reject all" on a cookie banner stop tracking cookies? When GPC and a banner choice conflict, which one wins?

## Scope

- **Sites:** popular domains from the Tranco list, filtered to US-relevant, English-language, commercial sites.
- **Pages:** the homepage plus up to two same-site internal pages.
- **Vantage point:** a California IP address, since many sites geo-gate CCPA behavior.
- **Repetitions:** three or more paired runs per site, because ad auctions are non-deterministic.
- **Out of scope:**
  - Logged-in tracking, and server-to-server data sharing (which is invisible to the browser).
  - Mobile apps, and legal questions of whether a site is a covered "business".

## GPC emulation

A GPC-enabled browser does two things, and GPCheck reproduces both:

- **Header:** it sends `Sec-GPC: 1` on every request (navigations, subresources, iframes).
- **JavaScript:** it exposes `navigator.globalPrivacyControl === true` in every frame.

`gpcheck check-gpc` verifies both against local test pages, including inside a cross-site iframe.

## Crawl protocol

For each site and run:

1. Open a fresh, empty browser context. No cookies or storage carry over.
2. Load the homepage, wait for the network to settle, then dwell for 15 seconds while scrolling, so lazy-loaded tags fire.
3. Visit up to two internal links with the same dwell. Every condition in a run uses the same links.
4. Record:
   - every request (URL, type, frame, `Sec-GPC` header, page index);
   - all cookies, and `localStorage` keys;
   - the site's US Privacy API (`__uspapi`), GPP (`__gpp`) and OneTrust consent state;
   - `/.well-known/gpc.json`.

The conditions for a site are visited back to back in a randomized order, which controls for time-varying ad inventory. The crawler uses a non-headless user agent, a US locale and the Pacific time zone.

## Conditions

| | GPC | Banner action | Purpose |
|---|---|---|---|
| A | off | none | baseline |
| B | on | none | GPC effect |
| C | off | Reject all | does rejecting work? |
| D | on | Accept all | does a later "accept" override GPC? |

Banner clicks use selectors for common CMPs (OneTrust, Cookiebot, Didomi, TrustArc, Quantcast, Usercentrics), with a fallback that matches button text.

## Classification

- **Third party:** the request's registrable domain (eTLD+1, from the Public Suffix List) belongs to a different organization than the site. Organization ownership comes from an entity map, so `youtube.com` on `google.com` is first party.
- **Tracker:** a third-party domain listed in DuckDuckGo Tracker Radar or Disconnect, or in the bundled seed list.
- **Tracking cookie:** a cookie whose name is a known marketing or analytics cookie (Open Cookie Database, or the seed list), or one set by a third-party tracker domain.
- **Declared opt-out:** any of the following:
  - a US Privacy string with `Y` in the opt-out position (e.g. `1YYN`);
  - GPP US-section `SaleOptOut`, `SharingOptOut` or `TargetedAdvertisingOptOut` set to 1;
  - OneTrust `isGpcEnabled=1`, or the targeting group turned off.

## Metrics and verdicts

For each site, the median over runs is taken of the distinct tracker domains and tracking cookies under each condition. The **noise floor** is the largest difference between two baseline (A) runs of the same site. A change only counts if it is larger than this.

| Verdict | Rule |
|---|---|
| `honors` | tracking drops beyond the noise floor, and an opt-out is declared |
| `declares_only` | an opt-out is declared, but tracking does not drop |
| `ignores` | no declared opt-out and no drop |
| `reduces_without_declaring` | tracking drops, but no opt-out is declared |
| `no_tracking_baseline` | no trackers or tracking cookies even with GPC off |
| `inconclusive` | visits failed or were blocked |

Across sites, the analysis also reports:

- a one-sided Wilcoxon signed-rank test on the paired tracker and cookie counts;
- an exact McNemar test on whether any tracker loads at all;
- a per-vendor persistence rate: the share of sites where a vendor still loads with GPC on.

## Validation

- **Test sites:** local fixture sites with known behavior (honors, ignores, declares but still tracks, never tracks, a working banner, a broken banner). `gpcheck selftest` crawls them and checks every verdict.
- **Manual check:** a random sample of real sites is also inspected by hand in a GPC-enabled browser, to estimate the precision of the automated verdicts.

## Code layout

```
gpcheck/crawler/    browser contexts (GPC on/off), visits, request recorder, banner clicks, scheduler
gpcheck/classify/   domains and entities, tracker lists, cookies, opt-out signal decoding
gpcheck/analysis/   per-visit metrics, verdicts, statistics, report
gpcheck/fixtures/   local test sites with known GPC behavior
```

Output is JSONL (raw visits), CSV, a DuckDB database and a Markdown report.

## Ethics

- No human subjects and no personal data: every session is synthetic.
- Crawling is low-rate, with a few page loads per site, and no logins or form submissions.
- Results are reported in aggregate. Individual sites are re-verified by hand before being named, and verdicts describe observed behavior, not legal conclusions.

## Limitations

- **Server-side sharing is invisible.** A clean result does not prove compliance; non-compliance findings are the strong claims.
- **The crawler may be treated differently from a real visitor,** because of bot detection or geolocation errors. Blocked visits are logged and excluded.
- **Tracker and cookie lists are incomplete.** List versions are recorded with each analysis.
- **Some sites apply the opt-out only after the first page load.** First-page and later-page trackers are reported separately.

## Related work

- The W3C Global Privacy Control specification.
- Prior GPC compliance measurements by Zimmeck et al.
- Cookie-banner studies: Matte, Bielova & Santos (IEEE S&P 2020); Nouwens et al. (CHI 2020); Bollinger et al. (USENIX Security 2022).
- Measurement methodology: OpenWPM, and the Tranco list (Le Pochat et al., NDSS 2019).

## Future work

- Longitudinal re-crawls after enforcement actions.
- Comparing California with other states that require universal opt-out signals.
- Parsing tracker request parameters, to see *what* data is sent and not just *whether* a request happens.
- Comparing privacy-policy claims about GPC with measured behavior.

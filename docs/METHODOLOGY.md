# Methodology

## Overview

California's CCPA (as amended by the CPRA) requires covered businesses to treat a browser's Global Privacy Control (GPC) signal as a request to opt out of the sale or sharing of personal information (11 CCR §7025). GPCheck tests whether sites actually do this. It visits each site under controlled conditions, once with GPC off and once with GPC on, and compares what the site does: third-party tracker requests, tracking cookies, and the opt-out status the site itself reports.

## Research questions

1. Among popular sites visited from California, what fraction change their tracking behavior when GPC is on?
2. Do sites that *declare* an opt-out (USP/GPP strings, CMP cookies, `/.well-known/gpc.json`) actually reduce tracking?
3. Which third parties keep receiving requests after the opt-out, and which CMPs and site categories are associated with non-compliance?
4. Does clicking "Reject all" on a cookie banner stop tracking cookies? When GPC and a banner choice conflict, which one wins?

## Scope

- **Sites:** 500 popular US consumer-facing commercial sites. The Tranco top list on its own is dominated by infrastructure (CDNs, DNS, APIs) and non-US domains, so the sample starts from a hand-drawn candidate list of 775 sites in 13 categories (`data/sites/candidates.csv`), and `gpcheck sites` keeps the 500 that rank highest in Tranco. Non-profits and government sites are left out, since the CCPA covers businesses. The candidate list and its category labels are a judgment call, so the sample is popular US sites, not a random draw from the web.
- **Pages:** the homepage plus up to two same-site internal pages.
- **Vantage point:** a California IP address, since many sites geo-gate CCPA behavior. The study covers California only.
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
2. Load the homepage (waiting up to 15 seconds for the `load` event, but not requiring it, since ad-heavy pages can take longer), wait for the network to settle, then dwell for 15 seconds while scrolling, so lazy-loaded tags fire.
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

A visit counts as **blocked**, and is excluded like a failed visit, when the homepage returns HTTP 401, 403, 429 or 503, or when the page title matches a known bot-challenge page ("Access Denied", "Just a moment...", and similar). Without this, a bot wall served under both conditions would look like a site with no trackers. A site with any blocked A or B visit is `inconclusive`, because the visits that get through may be degraded. For every site with a verdict, the report also gives the share of baseline tracker domains that still load with GPC on, since a drop beyond the noise floor can leave most trackers in place.

Across sites, the analysis also reports:

- a 95% Wilson score interval on each verdict share;
- the verdict mix per site category, when a `site,category` file is supplied;
- a one-sided Wilcoxon signed-rank test on the paired tracker and cookie counts;
- an exact McNemar test on whether any tracker loads at all;
- a per-vendor persistence rate: the share of sites where a vendor still loads with GPC on.

## Opt-out propagation to vendors

A site can honor GPC on the page and still send full tracking events to its vendors, or it can pass the opt-out downstream. With GPC on, each data-sending tracker request (beacons, XHR/fetch, pixels and iframes, but not script or style downloads) is checked for an opt-out signal. The URL and the request body (form, JSON or text, up to 4 KB) are both inspected:

- `us_privacy` with `Y` in the opt-out position;
- a GPC parameter (`gpc=1`);
- Google `npa=1` (non-personalized ads), `ltd=1` (limited ads) or `rdp=1` (restricted data processing);
- Meta `dpo=LDU` (Limited Data Use).

GPP strings (`gpp`, `gpp_sid`) and event names (for example `ev=Purchase`) are recorded as well. Each site gets a propagation verdict: `all_requests_carry_optout`, `some_requests_carry_optout` or `no_optout_passed`. The report also gives a per-vendor share of requests that carried the opt-out.

## Policy claims vs. measured behavior

`gpcheck policy` visits each site once, with GPC off, and records two things a consumer could rely on:

- **Opt-out link:** a "Do Not Sell or Share My Personal Information" or "Your Privacy Choices" link (Cal. Civ. Code §1798.135(a), 11 CCR §7015) on the homepage or the policy page.
- **Policy claim:** the privacy policy is located from the homepage links, and every sentence mentioning Global Privacy Control or an "opt-out preference signal" is classified as a commitment to honor it, a statement that it is not honored, or a bare mention. The sentence is kept as evidence.

Each site's claim is then joined to its measured verdict:

| Label | Policy | Measured |
|---|---|---|
| `claims_but_does_not_honor` | says GPC is honored | tracking does not drop |
| `claim_matches_behavior` | says GPC is honored | tracking drops |
| `no_claim_and_does_not_honor` | no commitment | tracking does not drop |
| `honors_without_claiming` | no commitment | tracking drops |

The first row is the policy-relevant one: a public statement that is contradicted by observed behavior is the pattern behind California's Sephora (2022) and Healthline (2025) enforcement actions. The report also lists sites that neither reduce tracking under GPC nor show an opt-out link. The text classifier is keyword-based, so every flagged sentence should be read by hand before a site is named.

## Vantage points (not used in this study)

The tool can compare locations, but this study does not: it needs the same crawl repeated from other states, and is left as future work. Each crawl is labeled with its vantage point (`gpcheck crawl --vantage CO`). At the start of a crawl, the machine's city, region and country are looked up and stored; the IP address is not stored. Running the same site list from California, from another state with an opt-out-signal law (e.g. Colorado, Texas), and from a state without one tests whether sites honor GPC only where they are legally required to. `gpcheck analyze` accepts several crawl files and reports the verdict mix per vantage point, plus the sites whose verdict changes between them.

## Validation

- **Test sites:** local fixture sites with known behavior (honors, ignores, declares but still tracks, never tracks, a bot wall, a working banner, a broken banner). `gpcheck selftest` crawls them and checks every verdict.

## Code layout

```
gpcheck/crawler/    browser contexts (GPC on/off), visits, request recorder, banner clicks, scheduler, policy check
gpcheck/classify/   domains and entities, tracker lists, cookies, opt-out signal decoding, policy text
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
- **Policy text is read by keyword.** A policy split across several pages, or one that describes GPC in unusual wording, can be misclassified, and pages under 1,500 characters are treated as unreadable.
- **Tracker and cookie lists are incomplete.** List versions are recorded with each analysis.
- **Some sites apply the opt-out only after the first page load.** First-page and later-page trackers are reported separately.

## Related work

- The W3C Global Privacy Control specification.
- Prior GPC compliance measurements by Zimmeck et al.
- Cookie-banner studies: Matte, Bielova & Santos (IEEE S&P 2020); Nouwens et al. (CHI 2020); Bollinger et al. (USENIX Security 2022).
- Measurement methodology: OpenWPM, and the Tranco list (Le Pochat et al., NDSS 2019).

## Future work

- Longitudinal re-crawls after enforcement actions.
- Repeating the crawl from states with and without an opt-out-signal law, to test whether sites honor GPC only where they must.
- Decoding GPP strings fully, and identifying which event types (page views vs. purchases) still flow.

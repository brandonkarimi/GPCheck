# Checking a site by hand

The automated verdicts need an independent check. This guide is for verifying a sample of sites yourself in a real browser. Each site takes about five minutes.

## Before you start

1. Draw the sample. The sheet lists sites only, without the automated verdicts, so your judgment is not influenced by them:

   ```bash
   gpcheck sample results/study_analysis/sites.csv --n 20 --out results/manual_check.csv
   ```

2. Use a Chromium-based browser from a California IP address, with no ad blocker or tracker blocking. Create two fresh profiles:
   - **Off:** a clean profile with no extensions.
   - **On:** a clean profile with only a GPC extension installed (for example OptMeowt), or Brave with GPC enabled and its Shields turned off for the site.

3. In the **On** profile, open the DevTools console on any page and confirm that `navigator.globalPrivacyControl` is `true`. In the **Off** profile it should be `undefined` or `false`.

## For each site

Do the same steps in both profiles, starting each from a new private window so no cookies carry over.

1. Open DevTools, go to the **Network** tab, and tick **Preserve log**.
2. Load the homepage. Do not click any cookie banner. Scroll to the bottom and wait about 15 seconds.
3. Note the third-party advertising and analytics domains you see (for example `doubleclick.net`, `google-analytics.com`, `facebook.com/tr`, `criteo.com`, `adnxs.com`). A rough count is enough: none, a few, or many.
4. In the **Application** tab, look at **Cookies** and note whether well-known tracking cookies are set (`_ga`, `_gid`, `_fbp`, `_gcl_au`, `IDE`).
5. In the **Console** of the **On** profile, check what the site says about your opt-out:

   ```js
   __uspapi('getUSPData', 1, d => console.log(d))                  // third character Y means opted out
   __gpp('ping', d => console.log(d))                              // GPP, if present
   document.cookie.match(/OptanonConsent=[^;]*/)?.[0]              // OneTrust: look for isGpcEnabled=1
   ```

   If none of these exist, the site declares nothing.

## Choosing a verdict

Compare the **Off** and **On** profiles and write one of these in the `manual_verdict` column:

| Verdict | Use it when |
|---|---|
| `honors` | Clearly fewer trackers or tracking cookies with GPC on, and the site declares an opt-out |
| `reduces_without_declaring` | Clearly fewer trackers or tracking cookies with GPC on, but the site declares nothing |
| `declares_only` | The site declares an opt-out, but the trackers and cookies look the same |
| `ignores` | Nothing declared and nothing changes |
| `no_tracking_baseline` | No trackers or tracking cookies even with GPC off |

Leave the row blank if the site blocks you or will not load. Use the `notes` column for anything unusual, such as a login wall or a banner that covers the page.

Ad auctions vary from load to load, so a difference of one or two domains is noise. If you are unsure, reload each profile once more before deciding.

## When you are done

```bash
gpcheck analyze results/study.jsonl --out results/study_analysis --manual results/manual_check.csv
```

The report gains a **Manual validation** section with the agreement rate, its confidence interval, Cohen's kappa and a list of the sites where you and the tool disagree. Those disagreements are the most useful output: look at each one to see whether the tool or the hand check was wrong, and why.

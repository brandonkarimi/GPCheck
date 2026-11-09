"""What a site *says* about opt-outs: its footer links and its privacy policy text."""

from __future__ import annotations

import re

# CCPA §1798.135(a): a "Do Not Sell or Share My Personal Information" link, or the
# alternative "Your Privacy Choices" link (11 CCR §7015).
OPT_OUT_LINK = re.compile(
    r"do\s*not\s*sell|don['’]?t\s*sell|do\s*not\s*share|your\s*privacy\s*choices|"
    r"your\s*(california\s*)?privacy\s*rights|opt[\s-]*out\s*of\s*(the\s*)?(sale|sharing)", re.I)
POLICY_LINK = re.compile(r"privacy\s*(policy|notice|statement|center|centre)|^\s*privacy\s*$", re.I)
NOT_A_POLICY = re.compile(r"choices|settings|preferences|manage|cookie", re.I)
# A page shorter than this is a stub, a consent wall or a shell that never rendered, not a policy.
MIN_POLICY_CHARS = 1500

GPC_MENTION = re.compile(r"global\s+privacy\s+control|\bGPC\b|opt[\s-]*out\s+preference\s+signal", re.I)
CALIFORNIA = re.compile(r"\bCCPA\b|\bCPRA\b|california\s+consumer\s+privacy|california\s+privacy\s+rights", re.I)
AFFIRM = re.compile(r"\b(honou?rs?|recogni[sz]es?|respects?|responds?|process(es)?|treats?|accepts?|"
                    r"supports?|comply|complies|appl(y|ies)|(to|can|may)\s+opt[\s-]*out)\b", re.I)
NEGATE = re.compile(r"\b(do(es)?\s+not|don['’]t|doesn['’]t|cannot|can['’]t|not\s+(currently|yet)|unable|no\s+longer)\b",
                    re.I)

CLAIM_TEXT = {
    "claims_to_honor_gpc": "Policy says GPC / opt-out preference signals are honored",
    "says_gpc_not_honored": "Policy says GPC is not honored",
    "mentions_gpc": "Policy mentions GPC without a clear commitment",
    "no_gpc_mention": "Policy found, but it never mentions GPC",
    "policy_not_found": "No privacy policy link found or page unreadable",
}
# Automated verdicts where tracking did not drop with GPC on.
NOT_HONORING = {"ignores", "declares_only"}


def pick_links(anchors: list[dict]) -> dict:
    """From [{text, href}], find the opt-out link and the privacy policy link."""
    opt_out = policy = fallback = None
    for a in anchors:
        text = " ".join((a.get("text") or "").split())
        href = a.get("href") or ""
        if not text or len(text) > 80:
            continue
        if OPT_OUT_LINK.search(text):
            opt_out = opt_out or {"text": text, "href": href}
        elif not href.startswith("http"):
            continue
        elif POLICY_LINK.search(text):
            policy = policy or {"text": text, "href": href}
        elif "privacy" in text.lower() and not NOT_A_POLICY.search(text):
            fallback = fallback or {"text": text, "href": href}  # e.g. "Privacy & Security Statement"
    return {"opt_out_link": opt_out, "policy_link": policy or fallback}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def classify_policy_text(text: str | None) -> dict:
    """Does the policy commit to honoring GPC? Keeps the sentence as evidence."""
    if not text or len(text) < MIN_POLICY_CHARS:
        return {"claim": "policy_not_found", "evidence": None, "mentions_california": False}
    mentions = [s for s in _sentences(text) if GPC_MENTION.search(s)]
    california = bool(CALIFORNIA.search(text))
    if not mentions:
        return {"claim": "no_gpc_mention", "evidence": None, "mentions_california": california}
    denied = next((s for s in mentions if NEGATE.search(s) and AFFIRM.search(s)), None)
    affirmed = next((s for s in mentions if AFFIRM.search(s) and not NEGATE.search(s)), None)
    if affirmed:
        claim, evidence = "claims_to_honor_gpc", affirmed
    elif denied:
        claim, evidence = "says_gpc_not_honored", denied
    else:
        claim, evidence = "mentions_gpc", mentions[0]
    return {"claim": claim, "evidence": evidence[:400], "mentions_california": california}


def says_vs_does(claim: str | None, verdict: str | None) -> str | None:
    """Label the combination of what the policy claims and what the crawl measured."""
    if not claim or not verdict or verdict in ("inconclusive", "no_tracking_baseline"):
        return None
    if claim == "claims_to_honor_gpc":
        return "claims_but_does_not_honor" if verdict in NOT_HONORING else "claim_matches_behavior"
    if verdict in NOT_HONORING:
        return "no_claim_and_does_not_honor"
    return "honors_without_claiming"

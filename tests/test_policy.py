from gpcheck.analysis.report import policy_by_site
from gpcheck.classify.policy import classify_policy_text, pick_links, says_vs_does

PAD = "We collect information about how you use our services and share it with partners. " * 25


def test_pick_links():
    links = pick_links([
        {"text": "About", "href": "https://shop.com/about"},
        {"text": "Privacy Policy", "href": "https://shop.com/privacy"},
        {"text": "Do Not Sell or Share My Personal Information", "href": "https://shop.com/optout"},
        {"text": "Privacy Notice", "href": "https://shop.com/other"},
    ])
    assert links["policy_link"]["href"] == "https://shop.com/privacy"
    assert links["opt_out_link"]["href"] == "https://shop.com/optout"
    assert pick_links([{"text": "Your Privacy Choices", "href": ""}])["opt_out_link"]
    assert pick_links([{"text": "Careers", "href": "https://shop.com/jobs"}]) == {"opt_out_link": None,
                                                                                 "policy_link": None}


def test_policy_claims():
    honors = classify_policy_text(PAD + "We honor Global Privacy Control signals as required by the CCPA.")
    assert honors["claim"] == "claims_to_honor_gpc" and "Global Privacy Control" in honors["evidence"]
    assert honors["mentions_california"]
    signal = classify_policy_text(PAD + "Our site recognizes opt-out preference signals sent by your browser.")
    assert signal["claim"] == "claims_to_honor_gpc"
    offers = classify_policy_text(PAD + "You may turn on the Global Privacy Control to opt out of the sale of data.")
    assert offers["claim"] == "claims_to_honor_gpc"
    refuses =classify_policy_text(PAD + "We do not currently respond to the Global Privacy Control.")
    assert refuses["claim"] == "says_gpc_not_honored"
    vague = classify_policy_text(PAD + "Some browsers offer a setting called Global Privacy Control.")
    assert vague["claim"] == "mentions_gpc"
    assert classify_policy_text(PAD)["claim"] == "no_gpc_mention"
    assert classify_policy_text("Access Denied")["claim"] == "policy_not_found"
    assert classify_policy_text(None)["claim"] == "policy_not_found"


def test_says_vs_does():
    assert says_vs_does("claims_to_honor_gpc", "declares_only") == "claims_but_does_not_honor"
    assert says_vs_does("claims_to_honor_gpc", "ignores") == "claims_but_does_not_honor"
    assert says_vs_does("claims_to_honor_gpc", "honors") == "claim_matches_behavior"
    assert says_vs_does("no_gpc_mention", "ignores") == "no_claim_and_does_not_honor"
    assert says_vs_does("no_gpc_mention", "reduces_without_declaring") == "honors_without_claiming"
    assert says_vs_does("claims_to_honor_gpc", "inconclusive") is None
    assert says_vs_does(None, "ignores") is None


def test_blocked_policy_visit_is_not_read_as_no_policy():
    blocked = {"site": "wall.com", "status": "ok", "pages": [{"status": 403}], "claim": "policy_not_found"}
    row = policy_by_site([blocked])["wall.com"]
    assert row["policy_readable"] is False and row["policy_claim"] is None and row["opt_out_link"] is None
